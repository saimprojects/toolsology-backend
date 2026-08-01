"""Reseller wallet services: credit (deposit), debit (purchase), activation."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from payments.models import IncomingSms
from payments.parser import normalize_trx
from payments.services import resolve_offer
from sourcing.models import Order
from sourcing import purchase_engine

from .models import Reseller, WalletTransaction


class WalletError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def get_or_create_reseller(user) -> Reseller:
    reseller, _ = Reseller.objects.get_or_create(user=user)
    return reseller


def _record(reseller: Reseller, kind: str, amount: Decimal, *,
            order=None, sms=None, note="") -> WalletTransaction:
    return WalletTransaction.objects.create(
        reseller=reseller, kind=kind, amount=amount,
        balance_after=reseller.wallet_balance, order=order, sms=sms, note=note,
    )


def topup_via_trx(reseller: Reseller, trx_id: str) -> WalletTransaction:
    """Credit the wallet from a one-time payment SMS matched by trx id."""
    trx_norm = normalize_trx(trx_id)
    if not trx_norm:
        raise WalletError("missing_trx", "Transaction ID is required.")

    with transaction.atomic():
        locked = Reseller.objects.select_for_update().get(pk=reseller.pk)
        sms = (
            IncomingSms.objects
            .select_for_update(skip_locked=True)
            .filter(trx_id=trx_norm, is_consumed=False)
            .order_by("received_at")
            .first()
        )
        if sms is None:
            if IncomingSms.objects.filter(trx_id=trx_norm, is_consumed=True).exists():
                raise WalletError("already_used", "This Transaction ID is already used.")
            raise WalletError(
                "not_found",
                "Payment not found yet. If you just paid, wait a moment and retry.",
            )
        if sms.amount is None or sms.amount <= 0:
            raise WalletError("bad_amount", "Could not read the paid amount from SMS.")

        locked.wallet_balance += sms.amount
        locked.refresh_activation()
        locked.save(update_fields=["wallet_balance", "is_activated", "activated_at"])

        sms.is_consumed = True
        sms.consumed_at = timezone.now()
        sms.save(update_fields=["is_consumed", "consumed_at"])

        txn = _record(locked, WalletTransaction.Kind.DEPOSIT, sms.amount,
                      sms=sms, note="Wallet top-up")
    return txn


def purchase_from_wallet(reseller: Reseller, *, product, offer_id: int,
                         quantity: int, idempotency_key: str,
                         customer_email: str = "",
                         slot_months: int | None = None) -> Order:
    """Deduct the chosen offer's reseller price from wallet, then buy it."""
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    kind, obj = resolve_offer(product, offer_id)
    if obj is None:
        raise WalletError("invalid_offer", "Selected plan is not available.")
    unit_price = obj.price_for("reseller")
    if unit_price is None:
        raise WalletError("not_for_sale", "This plan is not available for sale.")
    in_stock = obj.supplier_product.in_stock if kind == "bot" else obj.in_stock()
    if not in_stock:
        raise WalletError("out_of_stock", "This plan is out of stock.")
    total = (unit_price * Decimal(quantity)).quantize(Decimal("0.01"))

    with transaction.atomic():
        locked = Reseller.objects.select_for_update().get(pk=reseller.pk)
        if not locked.can_operate:
            raise WalletError(
                "not_activated",
                f"Deposit at least {locked.min_deposit} PKR to activate your panel.",
            )
        if locked.wallet_balance < total:
            raise WalletError(
                "insufficient_funds",
                f"Wallet balance too low. Price is {total}, top up first.",
            )

        order, _ = purchase_engine.get_or_create_order(
            idempotency_key=idempotency_key,
            product=product,
            quantity=quantity,
            buyer_type="reseller",
            user=locked.user,
            customer_email=customer_email,
            slot_months=slot_months,
            offer_label=obj.label(),
        )
        order.sell_amount_pkr = total
        order.save(update_fields=["sell_amount_pkr"])

        locked.wallet_balance -= total
        locked.save(update_fields=["wallet_balance"])
        _record(locked, WalletTransaction.Kind.PURCHASE, -total,
                order=order, note=f"Purchase: {product.title}")

    # Fulfil the chosen offer (outside the wallet lock).
    if kind == "bot":
        order = purchase_engine.purchase_offer(order, obj)
    else:
        order = purchase_engine.deliver_from_stock(order)

    # If fulfilment failed (no stock/all bots failed), refund the wallet.
    if order.status == Order.Status.FAILED:
        with transaction.atomic():
            locked = Reseller.objects.select_for_update().get(pk=reseller.pk)
            locked.wallet_balance += total
            locked.save(update_fields=["wallet_balance"])
            _record(locked, WalletTransaction.Kind.REFUND, total,
                    order=order, note="Auto-refund: fulfilment failed")
    return order
