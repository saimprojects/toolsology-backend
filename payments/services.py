"""Payment ingestion + verification services."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from sourcing.models import Order, ProductSourceLink, StockOffer
from sourcing import purchase_engine

from .models import IncomingSms, PaymentMethod
from .parser import normalize_trx, parse_sms


def resolve_offer(product, offer_token):
    """Resolve an offer token to (kind, obj).

    kind is 'bot' (ProductSourceLink), 'stock' (StockOffer), or None.
    Tokens look like 'bot-5' / 'stock-3'. A bare integer is treated as a bot
    link id for backward compatibility.
    """
    token = str(offer_token)
    if token.startswith("stock-"):
        so = StockOffer.objects.filter(
            id=token[6:], is_enabled=True, product=product).first()
        return ("stock", so)
    link_id = token[4:] if token.startswith("bot-") else token
    link = (
        ProductSourceLink.objects
        .select_related("supplier_product", "supplier_product__bot",
                        "product_sourcing")
        .filter(id=link_id, is_enabled=True, product_sourcing__product=product)
        .first()
    )
    return ("bot", link)


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
    offer_id: int,
    quantity: int,
    buyer_type: str,
    trx_id: str,
    idempotency_key: str,
    customer_email: str = "",
    slot_months: int | None = None,
    user=None,
) -> Order:
    """Match a trx id to an unconsumed SMS, then buy the CHOSEN offer.

    One-time guarantee: the matching IncomingSms is locked and flagged consumed
    inside a transaction, so the same trx id can never verify two orders.
    """
    trx_norm = normalize_trx(trx_id)
    if not trx_norm:
        raise PaymentError("missing_trx", "Transaction ID is required.")

    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    kind, obj = resolve_offer(product, offer_id)
    if obj is None:
        raise PaymentError("invalid_offer", "Selected plan is not available.")
    unit_price = obj.price_for(buyer_type)
    if unit_price is None:
        raise PaymentError("not_for_sale", "This plan is not available for sale.")
    in_stock = obj.supplier_product.in_stock if kind == "bot" else obj.in_stock()
    if not in_stock:
        raise PaymentError("out_of_stock", "This plan is out of stock.")

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
            if IncomingSms.objects.filter(trx_id=trx_norm, is_consumed=True).exists():
                raise PaymentError("already_used",
                                   "This Transaction ID has already been used.")
            raise PaymentError(
                "not_found",
                "Payment not found yet. If you just paid, wait a moment and retry.",
            )
        if sms.amount is None or sms.amount < expected_total:
            raise PaymentError(
                "amount_mismatch",
                f"Paid amount does not match the price (expected {expected_total}).",
            )

        order, _ = purchase_engine.get_or_create_order(
            idempotency_key=idempotency_key,
            product=product,
            quantity=quantity,
            buyer_type=buyer_type,
            user=user,
            customer_email=customer_email,
            slot_months=slot_months,
            offer_label=obj.label(),
        )
        order.sell_amount_pkr = expected_total
        order.save(update_fields=["sell_amount_pkr"])

        sms.is_consumed = True
        sms.consumed_at = timezone.now()
        sms.consumed_by_order = order
        sms.save(update_fields=["is_consumed", "consumed_at", "consumed_by_order"])

    # Fulfil the chosen offer (outside the payment lock).
    if kind == "bot":
        purchase_engine.purchase_offer(order, obj)
    else:
        purchase_engine.deliver_from_stock(order)
    return order
