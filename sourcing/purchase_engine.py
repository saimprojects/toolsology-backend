"""Fulfilment engine: own-stock-first, then cheapest bot with safe fallback.

Fallback rules (deliberate):
  * Definitive failure on a bot (insufficient balance / not found / inventory /
    invalid key) => try the NEXT cheapest bot.
  * Ambiguous failure (network timeout / connection loss / 5xx) => STOP and mark
    the order 'needs_review'. We must not buy from another bot, because the first
    bot MIGHT already have charged and delivered. A human reconciles.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .canboso import (
    CanbosoAuthError,
    CanbosoBadRequest,
    CanbosoClient,
    CanbosoInventoryError,
    CanbosoNetworkError,
    CanbosoNotFound,
)
from .models import (
    DeliveredAccount,
    Order,
    ProductSourcing,
    SourcingSettings,
    StockItem,
)

SLOT_PRODUCT_ID = "slot_chatgpt_business"


def get_or_create_order(*, idempotency_key: str, product, quantity: int,
                        buyer_type: str, user=None, customer_email: str = "",
                        slot_months: int | None = None) -> tuple[Order, bool]:
    """Idempotent order creation. Returns (order, created)."""
    order, created = Order.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "product": product,
            "quantity": quantity,
            "buyer_type": buyer_type,
            "user": user,
            "customer_email": customer_email,
            "slot_months": slot_months,
        },
    )
    return order, created


def _sourcing_for(product) -> ProductSourcing:
    sourcing, _ = ProductSourcing.objects.get_or_create(product=product)
    return sourcing


def _try_own_stock(order: Order) -> bool:
    """Deliver from own stock if enough is available. Returns True if fulfilled."""
    with transaction.atomic():
        items = list(
            StockItem.objects.select_for_update(skip_locked=True)
            .filter(product=order.product, is_sold=False)[: order.quantity]
        )
        if len(items) < order.quantity:
            return False
        now = timezone.now()
        for item in items:
            item.is_sold = True
            item.sold_at = now
            item.save(update_fields=["is_sold", "sold_at"])
            DeliveredAccount.objects.create(
                order=order,
                username=item.username,
                password=item.password,
                verify_email=item.verify_email,
            )
        order.source = Order.Source.OWN_STOCK
        order.status = Order.Status.COMPLETED
        order.save(update_fields=["source", "status"])
    return True


def _buy_from_bot(order: Order, link) -> str:
    """Attempt a purchase from one bot.

    Returns one of: 'ok', 'try_next', 'stop'.
    """
    sp = link.supplier_product
    bot = sp.bot
    client = CanbosoClient(api_key=bot.api_key, base_url=bot.base_url)

    is_slot = sp.is_slot or sp.remote_id == SLOT_PRODUCT_ID
    try:
        if is_slot:
            resp = client.purchase(
                sp.remote_id,
                customer_email=order.customer_email,
                slot_months=order.slot_months,
            )
        else:
            resp = client.purchase(
                sp.remote_id,
                quantity=order.quantity * link.buy_quantity,
            )
    except CanbosoNetworkError as exc:
        # Ambiguous — do NOT fall back.
        order.status = Order.Status.NEEDS_REVIEW
        order.fulfilled_bot = bot
        order.error_message = f"Ambiguous on {bot.name}: {exc.message}"[:255]
        order.save(update_fields=["status", "fulfilled_bot", "error_message"])
        return "stop"
    except (CanbosoBadRequest, CanbosoNotFound, CanbosoInventoryError,
            CanbosoAuthError) as exc:
        # Definitive failure — safe to try the next bot.
        order.error_message = f"{bot.name}: {exc.message}"[:255]
        order.save(update_fields=["error_message"])
        return "try_next"

    # Success.
    for acc in resp.get("deliveredAccounts", []) or []:
        DeliveredAccount.objects.create(
            order=order,
            username=acc.get("user", "") or "",
            password=acc.get("password", "") or "",
            verify_email=acc.get("verifyEmail", "") or "",
        )
    order.source = Order.Source.BOT
    order.fulfilled_bot = bot
    order.status = Order.Status.COMPLETED
    order.cost_amount = resp.get("amount")
    order.cost_currency = resp.get("walletCurrency", "") or ""
    order.canboso_order_code = resp.get("orderCode", "") or ""
    order.raw_response = resp
    order.error_message = ""
    order.save()
    return "ok"


def _ranked_links(sourcing: ProductSourcing):
    """Enabled, in-stock links on active bots, cheapest USD first."""
    links = [
        l for l in sourcing.links.filter(is_enabled=True)
        .select_related("supplier_product", "supplier_product__bot")
        if l.supplier_product
        and l.supplier_product.usd_pricing is not None
        and l.supplier_product.in_stock
        and l.supplier_product.bot.is_active
    ]
    return sorted(
        links,
        key=lambda l: (l.supplier_product.usd_pricing,
                       l.supplier_product.bot.priority),
    )


def fulfill(order: Order) -> Order:
    """Run the full fulfilment flow for a pending order."""
    if order.status != Order.Status.PENDING:
        return order  # already processed — idempotent

    sourcing = _sourcing_for(order.product)
    settings = SourcingSettings.load()

    # Record the selling price at time of order.
    if order.sell_amount_pkr is None:
        order.sell_amount_pkr = sourcing.price_for(order.buyer_type)
        order.save(update_fields=["sell_amount_pkr"])

    # 1) Own stock first.
    if settings.prefer_own_stock and _try_own_stock(order):
        return order

    # 2) Bots, cheapest first, with safe fallback.
    for link in _ranked_links(sourcing):
        outcome = _buy_from_bot(order, link)
        if outcome in ("ok", "stop"):
            return order
        # 'try_next' -> continue loop

    # Nothing delivered and nothing ambiguous.
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.FAILED
        if not order.error_message:
            order.error_message = "No stock and no bot could fulfil this order."
        order.save(update_fields=["status", "error_message"])
    return order
