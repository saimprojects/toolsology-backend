"""Service layer for the sourcing app.

Right now this covers *syncing* a bot's catalogue + balance into the DB so
prices can be compared and shown in admin. The purchase/fallback engine is
built on top of this once product-mapping is decided.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

import re

from .canboso import CanbosoError
from .models import (
    ProductSourceLink,
    ProductSourcing,
    SupplierBot,
    SupplierProduct,
)
from .providers import client_for_bot


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def sync_bot(bot: SupplierBot) -> dict:
    """Pull /products (+ wallet balance) for one bot and cache it.

    Returns a small summary dict. Raises nothing to the caller for a routine
    API error — it records the error on the bot and returns it in the summary,
    so a single bad key doesn't blow up a bulk sync.
    """
    client = client_for_bot(bot)
    summary = {"bot": bot.name, "synced": 0, "error": ""}

    try:
        data = client.list_products()
    except CanbosoError as exc:
        bot.last_sync_error = f"{type(exc).__name__}: {exc.message}"[:255]
        bot.last_synced = timezone.now()
        bot.save(update_fields=["last_sync_error", "last_synced"])
        summary["error"] = bot.last_sync_error
        return summary

    wallet_currency = data.get("walletCurrency", "") or ""
    products = data.get("products")
    if not isinstance(products, list):
        bot.last_sync_error = "Invalid supplier response: products must be a list."
        bot.last_synced = timezone.now()
        bot.save(update_fields=["last_sync_error", "last_synced"])
        summary["error"] = bot.last_sync_error
        return summary

    # A transient upstream/WAF problem can occasionally be returned as a
    # successful but empty catalogue. Never wipe a previously healthy cache.
    if not products and bot.products.exists():
        bot.last_sync_error = "Supplier returned an unexpected empty catalogue; cached products were preserved."
        bot.last_synced = timezone.now()
        bot.save(update_fields=["last_sync_error", "last_synced"])
        summary["error"] = bot.last_sync_error
        return summary

    seen_ids: list[str] = []
    synced_at = timezone.now()
    with transaction.atomic():
        for p in products:
            remote_id = p.get("_id")
            if not remote_id:
                continue
            remote_id = str(remote_id)
            seen_ids.append(remote_id)
            stats = p.get("stats") or {}
            SupplierProduct.objects.update_or_create(
                bot=bot,
                remote_id=remote_id,
                defaults={
                    "name": p.get("product_name", "") or "",
                    "name_raw": p.get("product_name_raw", "") or "",
                    "wallet_currency": p.get("walletCurrency", wallet_currency) or "",
                    "wallet_pricing": _dec(p.get("walletPricing", p.get("pricing"))),
                    "usd_pricing": _dec(p.get("usdPricing")),
                    "available": stats.get("available"),
                    "is_slot": bool(p.get("isSlotProduct", False)),
                    "slot_durations": p.get("slotDurations") or [],
                    "raw": p,
                    "last_synced": synced_at,
                },
            )

        # Preserve local links when a supplier removes an item; it immediately
        # becomes unavailable and can reappear on a later sync without remapping.
        if seen_ids:
            SupplierProduct.objects.filter(bot=bot).exclude(
                remote_id__in=seen_ids
            ).update(available=0, last_synced=synced_at)

    # Refresh cached wallet balance (best-effort).
    balance_text = ""
    balance_val = None
    try:
        bal = client.get_balance()
        balance_val = _dec(bal.get("balance"))
        balance_text = bal.get("balanceText", "") or ""
        if not wallet_currency:
            wallet_currency = bal.get("walletCurrency", "") or ""
    except CanbosoError:
        pass  # balance is non-critical for a catalogue sync

    bot.wallet_currency = wallet_currency
    bot.last_balance = balance_val
    bot.last_balance_text = balance_text
    bot.last_sync_error = ""
    bot.last_synced = timezone.now()
    bot.save(update_fields=[
        "wallet_currency", "last_balance", "last_balance_text",
        "last_sync_error", "last_synced",
    ])

    summary["synced"] = len(seen_ids)
    return summary


def sync_all_active_bots() -> list[dict]:
    return [sync_bot(bot) for bot in SupplierBot.objects.filter(is_active=True)]


# ---------------------------------------------------------------------------
# Auto-matching local products to bot products by name
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def auto_match(sourcing: ProductSourcing) -> int:
    """Create AUTO links for bot products whose name matches the local product.

    Never touches MANUAL links and never duplicates an existing link.
    Returns the number of new auto-links created.
    """
    if not sourcing.auto_match_enabled:
        return 0

    target = _norm(sourcing.product.title)
    existing_ids = set(
        sourcing.links.values_list("supplier_product_id", flat=True)
    )
    created = 0
    for sp in SupplierProduct.objects.filter(bot__is_active=True):
        if sp.id in existing_ids:
            continue
        if _norm(sp.name) == target or _norm(sp.name_raw) == target:
            ProductSourceLink.objects.create(
                product_sourcing=sourcing,
                supplier_product=sp,
                match_type=ProductSourceLink.MatchType.AUTO,
            )
            created += 1
    return created


def auto_match_all() -> int:
    total = 0
    for sourcing in ProductSourcing.objects.filter(auto_match_enabled=True):
        total += auto_match(sourcing)
    return total
