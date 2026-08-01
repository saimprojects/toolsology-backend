"""Payment ingestion + verification services."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from sourcing.models import Order, ProductSourcing
from sourcing import purchase_engine

from .models import IncomingSms, PaymentMethod
from .parser import normalize_trx, parse_sms


class PaymentError(Exception):
    """Verification failed for a reason worth showing the customer."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Ingestion (webhook)
# ---------------------------------------------------------------------------

def store_incoming_sms(raw_message: str, sender: str = "") -> IncomingSms:
    trx_id, amount = parse_sms(raw_message)

    method = None
    if sender:
        for m in PaymentMethod.objects.filter(is_active=True):
            if any(s.lower() in sender.lower() for s in m.sender_list()):
                method = m
                break

    return IncomingSms.objects.create(
        raw_message=raw_message,
        sender=sender or "",
        trx_id=normalize_trx(trx_id),
        amount=amount,
        method=method,
    )


# ---------------------------------------------------------------------------
# Verification + fulfilment
# ---------------------------------------------------------------------------

def verify_and_fulfill(
    *,
    product,
    quantity: int,
    buyer_type: str,
    trx_id: str,
    idempotency_key: str,
    customer_email: str = "",
    slot_months: int | None = None,
    user=None,
) -> Order:
    """Match a trx id to an unconsumed payment SMS, then fulfil the order.

    One-time guarantee: the matching IncomingSms is locked and flagged consumed
    inside a transaction, so the same trx id can never verify two orders.
    """
    trx_norm = normalize_trx(trx_id)
    if not trx_norm:
        raise PaymentError("missing_trx", "Transaction ID is required.")

    # If this checkout already produced an order (retry), return it as-is.
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    sourcing, _ = ProductSourcing.objects.get_or_create(product=product)
    unit_price = sourcing.price_for(buyer_type)
    if unit_price is None:
        raise PaymentError("not_for_sale", "This product is not available for sale.")
    if not sourcing.has_source():
        raise PaymentError("out_of_stock", "This product is currently out of stock.")

    expected_total = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

    with transaction.atomic():
        sms = (
            IncomingSms.objects
            .select_for_update(skip_locked=True)
            .filter(trx_id=trx_norm, is_consumed=False)
            .order_by("received_at")
            .first()
        )
        if sms is None:
            # Either not received yet, or already used.
            if IncomingSms.objects.filter(trx_id=trx_norm, is_consumed=True).exists():
                raise PaymentError(
                    "already_used",
                    "This Transaction ID has already been used.",
                )
            raise PaymentError(
                "not_found",
                "Payment not found yet. If you just paid, wait a moment and retry.",
            )

        if sms.amount is None or sms.amount < expected_total:
            raise PaymentError(
                "amount_mismatch",
                f"Paid amount does not match the price (expected {expected_total}).",
            )

        # Consume the SMS (one-time) and create the order atomically.
        order, _ = purchase_engine.get_or_create_order(
            idempotency_key=idempotency_key,
            product=product,
            quantity=quantity,
            buyer_type=buyer_type,
            user=user,
            customer_email=customer_email,
            slot_months=slot_months,
        )
        order.sell_amount_pkr = expected_total
        order.save(update_fields=["sell_amount_pkr"])

        sms.is_consumed = True
        sms.consumed_at = timezone.now()
        sms.consumed_by_order = order
        sms.save(update_fields=["is_consumed", "consumed_at", "consumed_by_order"])

    # Fulfil outside the payment lock (own stock -> cheapest bot -> fallback).
    purchase_engine.fulfill(order)
    return order
