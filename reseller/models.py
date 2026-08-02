from __future__ import annotations

from decimal import Decimal

from django.conf import settings as dj_settings
from django.db import models
from django.utils import timezone
import hashlib
import secrets

from sourcing.models import SourcingSettings


class Reseller(models.Model):
    """A reseller-panel account with its own prepaid wallet.

    Activation: a reseller must deposit at least the global minimum (default
    2000 PKR) to activate the panel. After activation the account stays active;
    the wallet balance is fully spendable on purchases and can be topped up.
    Admin can waive the deposit (deposit_required=False) or let a reseller buy
    without the wallet (wallet_required=False).
    """

    user = models.OneToOneField(
        dj_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="reseller",
    )
    wallet_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Reseller's own money. Spendable on purchases. Not our income.",
    )
    is_activated = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)

    deposit_required = models.BooleanField(
        default=True,
        help_text="If off, this reseller can operate without the minimum deposit.",
    )
    wallet_required = models.BooleanField(
        default=True,
        help_text="If off, this reseller may pay per order (SMS) instead of wallet.",
    )

    phone = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Reseller"
        verbose_name_plural = "Resellers"

    def __str__(self) -> str:
        return f"{self.user.username} (wallet {self.wallet_balance})"

    @property
    def min_deposit(self) -> Decimal:
        return SourcingSettings.load().reseller_min_deposit

    def refresh_activation(self) -> None:
        """Activate if the deposit requirement is met (or waived). One-way."""
        if self.is_activated:
            return
        if not self.deposit_required or self.wallet_balance >= self.min_deposit:
            self.is_activated = True
            self.activated_at = timezone.now()

    @property
    def can_operate(self) -> bool:
        return self.is_activated or not self.deposit_required


class WalletTransaction(models.Model):
    """Immutable audit log of every wallet movement."""

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        PURCHASE = "purchase", "Purchase"
        REFUND = "refund", "Refund"
        ADJUSTMENT = "adjustment", "Admin adjustment"

    reseller = models.ForeignKey(
        Reseller, related_name="transactions", on_delete=models.CASCADE
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Positive = credit, negative = debit.",
    )
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    order = models.ForeignKey(
        "sourcing.Order", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wallet_transactions",
    )
    sms = models.ForeignKey(
        "payments.IncomingSms", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wallet_transactions",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reseller.user.username} {self.kind} {self.amount}"


class ResellerApiKey(models.Model):
    reseller = models.ForeignKey(Reseller, related_name="api_keys", on_delete=models.CASCADE)
    name = models.CharField(max_length=80, default="Primary")
    prefix = models.CharField(max_length=12, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def issue(cls, reseller, name="Primary"):
        raw = "tsk_live_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(
            reseller=reseller, name=name, prefix=raw[:12],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        )
        return obj, raw

    @classmethod
    def authenticate(cls, raw):
        if not raw:
            return None
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return cls.objects.select_related("reseller", "reseller__user").filter(
            prefix=raw[:12], key_hash=digest, is_active=True
        ).first()

    def __str__(self):
        return f"{self.reseller.user.username} · {self.name} · {self.prefix}…"
