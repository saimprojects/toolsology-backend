"""Fulfilment engine.

The user now picks a SPECIFIC offer (one attached bot product) at checkout, so
there is no cheapest-selection and no cross-bot fallback: we buy exactly the
chosen offer. Outcomes:
  * success            -> order completed, credentials delivered
  * definitive failure -> order failed (insufficient balance / no stock / 404)
  * ambiguous (timeout)-> order needs_review (never assume it failed)
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
from .models import DeliveredAccount, Order, StockItem

SLOT_PRODUCT_ID = "slot_chatgpt_business"


def get_or_create_order(*, idempotency_key: str, product, quantity: int,
                        buyer_type: str, user=None, customer_email: str = "",
                        slot_months: int | None = None,
                        offer_label: str = "") -> tuple[Order, bool]:
    """Idempotent order creation. Returns (order, created)."""
    return Order.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "product": product,
            "quantity": quantity,
            "buyer_type": buyer_type,
            "user": user,
            "customer_email": customer_email,
            "slot_months": slot_months,
            "offer_label": offer_label,
        },
    )


def deliver_from_stock(order: Order) -> Order:
    """Fulfil an order from the product's own pre-loaded stock."""
    if order.status != Order.Status.PENDING:
        return order

    with transaction.atomic():
        items = list(
            StockItem.objects.select_for_update(skip_locked=True)
            .filter(product=order.product, is_sold=False)[: order.quantity]
        )
        if len(items) < order.quantity:
            order.status = Order.Status.FAILED
            order.error_message = "Out of stock."
            order.save(update_fields=["status", "error_message"])
            return order

        now = timezone.now()
        for item in items:
            data = item.as_dict()
            item.is_sold = True
            item.sold_at = now
            item.save(update_fields=["is_sold", "sold_at"])
            DeliveredAccount.objects.create(
                order=order,
                username=data.get("Username") or data.get("Email") or "",
                password=data.get("Password") or "",
                verify_email=data.get("Verify email") or data.get("Recovery") or "",
                details=data,
            )
        order.status = Order.Status.COMPLETED
        order.source = Order.Source.OWN_STOCK
        order.error_message = ""
        order.save(update_fields=["status", "source", "error_message"])
    return order


def purchase_offer(order: Order, link) -> Order:
    """Buy the exact supplier product behind `link`. No fallback."""
    if order.status != Order.Status.PENDING:
        return order  # already processed — idempotent

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
        order.status = Order.Status.NEEDS_REVIEW
        order.fulfilled_bot = bot
        order.error_message = f"Ambiguous on {bot.name}: {exc.message}"[:255]
        order.save(update_fields=["status", "fulfilled_bot", "error_message"])
        return order
    except (CanbosoBadRequest, CanbosoNotFound, CanbosoInventoryError,
            CanbosoAuthError) as exc:
        order.status = Order.Status.FAILED
        order.fulfilled_bot = bot
        order.error_message = f"{bot.name}: {exc.message}"[:255]
        order.save(update_fields=["status", "fulfilled_bot", "error_message"])
        return order

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
    return order
