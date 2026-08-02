from __future__ import annotations

from django.db import models
from cloudinary.models import CloudinaryField
from django.core.validators import MinValueValidator
from django.utils import timezone


class PaymentMethod(models.Model):
    """A bank / wallet account shown to customers so they know where to pay."""

    name = models.CharField(
        max_length=100, help_text="e.g. JazzCash, EasyPaisa, Meezan Bank."
    )
    account_title = models.CharField(
        max_length=150, help_text="Account holder name."
    )
    account_number = models.CharField(
        max_length=64, help_text="Account / wallet number or IBAN."
    )
    icon = CloudinaryField("icon", blank=True, null=True)
    instructions = models.TextField(
        blank=True, default="",
        help_text="Shown to the customer, e.g. 'Send exact amount, then enter TID'.",
    )
    sender_ids = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Comma-separated SMS senders to auto-match, e.g. '8558,JazzCash'.",
    )
    is_active = models.BooleanField(default=True)
    ordering = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ordering", "name"]
        verbose_name = "Payment Method"
        verbose_name_plural = "Payment Methods"

    def __str__(self) -> str:
        return f"{self.name} — {self.account_number}"

    def sender_list(self) -> list[str]:
        return [s.strip() for s in self.sender_ids.split(",") if s.strip()]


class PromoCode(models.Model):
    """Changes retail markup over platform cost; it is not a sale discount."""

    code = models.CharField(max_length=40, unique=True)
    product = models.ForeignKey(
        "product.Product", null=True, blank=True, on_delete=models.CASCADE,
        related_name="promo_codes", help_text="Blank applies to every product.",
    )
    markup_percent = models.DecimalField(
        max_digits=7, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Percentage added on top of platform/base cost.",
    )
    markup_flat_pkr = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        help_text="Flat PKR added after the percentage markup.",
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    times_used = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def is_available(self, product=None):
        now = timezone.now()
        return bool(
            self.is_active
            and (not self.starts_at or self.starts_at <= now)
            and (not self.expires_at or self.expires_at >= now)
            and (self.max_uses is None or self.times_used < self.max_uses)
            and (self.product_id is None or product is None or self.product_id == product.id)
        )

    def __str__(self):
        return self.code


class IncomingSms(models.Model):
    """A payment SMS forwarded from the Android gateway app.

    Stored raw; trx_id + amount are parsed best-effort. `is_consumed` enforces
    one-time use: once a trx id verifies an order it can never verify again.
    """

    raw_message = models.TextField()
    sender = models.CharField(max_length=64, blank=True, default="")

    trx_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    method = models.ForeignKey(
        PaymentMethod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="messages",
    )

    is_consumed = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_by_order = models.ForeignKey(
        "sourcing.Order", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="payment_sms",
    )

    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at"]
        verbose_name = "Incoming SMS"
        verbose_name_plural = "Incoming SMS"

    def __str__(self) -> str:
        return f"{self.trx_id or '??'} — {self.amount or '?'} ({self.sender})"


class BinanceDeposit(models.Model):
    """A successful Binance deposit consumed exactly once by this site."""

    tx_id = models.CharField(max_length=160, unique=True, db_index=True)
    coin = models.CharField(max_length=16, default="USDT")
    network = models.CharField(max_length=32, blank=True, default="")
    address = models.CharField(max_length=256, blank=True, default="")
    amount = models.DecimalField(max_digits=24, decimal_places=8)
    amount_pkr = models.DecimalField(max_digits=14, decimal_places=2)
    order = models.ForeignKey(
        "sourcing.Order", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="binance_payments",
    )
    reseller = models.ForeignKey(
        "reseller.Reseller", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="binance_deposits",
    )
    raw_data = models.JSONField(default=dict, blank=True)
    consumed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-consumed_at"]

    def __str__(self):
        return f"{self.coin} {self.amount} — {self.tx_id}"
