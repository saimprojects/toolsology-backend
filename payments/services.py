"""Payment ingestion + verification services."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

from django.db import transaction
from django.utils import timezone

from sourcing.models import Order, ProductSourceLink, StockOffer
from sourcing import purchase_engine

from .binance import BinanceError, find_pay_transaction, find_successful_deposit, pkr_to_coin
from .models import BinanceDeposit, IncomingSms, PaymentMethod, PromoCode
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


def promo_price_for_offer(*, product, offer_token, promo_code, quantity=1):
    """Return (promo, regular_total, promo_total) from platform cost + promo markup."""
    code = str(promo_code or "").strip().upper()
    if not code:
        return None, None, None
    promo = PromoCode.objects.filter(code=code).first()
    if not promo or not promo.is_available(product):
        raise PaymentError("invalid_promo", "Promo code is invalid, expired or no longer available.")
    kind, obj = resolve_offer(product, offer_token)
    if obj is None:
        raise PaymentError("invalid_offer", "Selected plan is not available.")
    regular = obj.price_for("retail")
    base = obj.cost_pkr() if kind == "bot" else obj.reseller_price
    if base is None or regular is None:
        raise PaymentError("promo_unavailable", "Promo pricing is unavailable for this plan.")
    unit = (base * (Decimal("1") + promo.markup_percent / Decimal("100"))
            + promo.markup_flat_pkr).quantize(Decimal("1"), rounding=ROUND_CEILING)
    qty = Decimal(quantity)
    return promo, (regular * qty).quantize(Decimal("0.01")), (unit * qty).quantize(Decimal("0.01"))


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
    payment_type: str = "local",
    promo_code: str = "",
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

    promo = None
    expected_total = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))
    if buyer_type == "retail" and promo_code:
        promo, _, expected_total = promo_price_for_offer(
            product=product, offer_token=offer_id, promo_code=promo_code, quantity=quantity,
        )

    if payment_type in {"binance", "binance_id"}:
        if BinanceDeposit.objects.filter(tx_id__iexact=trx_id.strip()).exists():
            raise PaymentError("already_used", "This Binance TxID has already been used.")
        try:
            deposit_data = (find_pay_transaction(trx_id) if payment_type == "binance_id"
                            else find_successful_deposit(trx_id))
            paid_coin = Decimal(str(deposit_data.get("amount", "0")))
            expected_coin = pkr_to_coin(expected_total)
        except BinanceError as exc:
            raise PaymentError(exc.code, exc.message) from exc
        except Exception as exc:
            raise PaymentError("bad_amount", "Binance returned an invalid deposit amount.") from exc
        if paid_coin < expected_coin:
            raise PaymentError(
                "amount_mismatch",
                f"Paid amount is too low (expected at least {expected_coin} {deposit_data.get('coin') or deposit_data.get('currency', 'USDT')}).",
            )

        with transaction.atomic():
            if promo:
                promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
                if not promo.is_available(product):
                    raise PaymentError("invalid_promo", "Promo code is no longer available.")
            if BinanceDeposit.objects.select_for_update().filter(tx_id__iexact=trx_id.strip()).exists():
                raise PaymentError("already_used", "This Binance TxID has already been used.")
            order, _ = purchase_engine.get_or_create_order(
                idempotency_key=idempotency_key, product=product, quantity=quantity,
                buyer_type=buyer_type, user=user, customer_email=customer_email,
                slot_months=slot_months, offer_label=obj.label(),
            )
            order.sell_amount_pkr = expected_total
            order.promo_code = promo.code if promo else ""
            order.save(update_fields=["sell_amount_pkr", "promo_code"])
            if promo:
                promo.times_used += 1
                promo.save(update_fields=["times_used"])
            BinanceDeposit.objects.create(
                tx_id=str(deposit_data.get("txId") or deposit_data.get("transactionId") or trx_id).strip(),
                coin=str(deposit_data.get("coin") or deposit_data.get("currency", "USDT")),
                network=("BINANCE_PAY" if payment_type == "binance_id" else str(deposit_data.get("network", ""))),
                address=(str((deposit_data.get("receiverInfo") or {}).get("binanceId", ""))
                         if payment_type == "binance_id" else str(deposit_data.get("address", ""))),
                amount=paid_coin, amount_pkr=expected_total,
                order=order, raw_data=deposit_data,
            )
        if kind == "bot":
            purchase_engine.purchase_offer(order, obj)
        else:
            purchase_engine.deliver_from_stock(order)
        return order

    with transaction.atomic():
        if promo:
            promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
            if not promo.is_available(product):
                raise PaymentError("invalid_promo", "Promo code is no longer available.")
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
        order.promo_code = promo.code if promo else ""
        order.save(update_fields=["sell_amount_pkr", "promo_code"])
        if promo:
            promo.times_used += 1
            promo.save(update_fields=["times_used"])

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
