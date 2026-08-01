from __future__ import annotations

from decimal import Decimal

from django.conf import settings as dj_settings
from django.db import models

from product.models import Product


class SupplierBot(models.Model):
    """A single Canboso buyer key = one bot wallet.

    You attach several of these (Telegram primary, Telegram 2nd, Binance,
    Bybit, ...). The purchase engine compares their prices per product and
    buys from the cheapest one that has stock, falling back to the next.
    """

    class BotSource(models.TextChoices):
        PRIMARY = "primary", "Telegram (primary)"
        TELEGRAM2 = "telegram2", "Telegram (2nd)"
        BINANCE = "binance", "Binance bot"
        BYBIT = "bybit", "Bybit bot"
        OTHER = "other", "Other"

    name = models.CharField(
        max_length=100,
        help_text="Label to recognise this bot, e.g. 'Telegram Primary'.",
    )
    bot_source = models.CharField(
        max_length=20,
        choices=BotSource.choices,
        default=BotSource.OTHER,
        help_text="Informational only; the key itself decides the real flow.",
    )
    api_key = models.CharField(
        max_length=255,
        help_text="Canboso buyer key (tgb_...). Kept server-side only.",
    )
    base_url = models.CharField(max_length=255, default="https://canboso.com")

    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck to exclude this bot from price comparison / purchases.",
    )
    priority = models.PositiveIntegerField(
        default=100,
        help_text="Tie-breaker when two bots have the same price. Lower = preferred.",
    )

    # Cached wallet info (refreshed on sync) — never authoritative for a purchase.
    wallet_currency = models.CharField(max_length=8, blank=True, default="")
    last_balance = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    last_balance_text = models.CharField(max_length=64, blank=True, default="")
    last_synced = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "name"]
        verbose_name = "Supplier Bot"
        verbose_name_plural = "Supplier Bots"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_bot_source_display()})"

    def masked_key(self) -> str:
        if not self.api_key:
            return ""
        return f"{self.api_key[:6]}…{self.api_key[-4:]}"


class SupplierProduct(models.Model):
    """A product as offered by one bot, cached from GET /products.

    `usd_pricing` is the common yardstick used to compare rates across bots
    that may quote in different wallet currencies (VND vs USD).
    """

    bot = models.ForeignKey(
        SupplierBot, related_name="products", on_delete=models.CASCADE
    )
    remote_id = models.CharField(
        max_length=64,
        help_text="Canboso product _id (or 'slot_chatgpt_business').",
    )
    name = models.CharField(max_length=255)
    name_raw = models.CharField(max_length=255, blank=True, default="")

    wallet_currency = models.CharField(max_length=8, blank=True, default="")
    wallet_pricing = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        help_text="Price in the bot's wallet currency.",
    )
    usd_pricing = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        help_text="Price in USD — used to compare across bots.",
    )
    available = models.IntegerField(
        null=True, blank=True,
        help_text="Stock available on this bot (null = unknown / unlimited).",
    )

    is_slot = models.BooleanField(default=False)
    slot_durations = models.JSONField(default=list, blank=True)

    raw = models.JSONField(
        default=dict, blank=True,
        help_text="Full product object as returned by Canboso.",
    )
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name", "usd_pricing"]
        unique_together = ("bot", "remote_id")
        verbose_name = "Supplier Product"
        verbose_name_plural = "Supplier Products"

    def __str__(self) -> str:
        return f"{self.name} @ {self.bot.name}"

    @property
    def in_stock(self) -> bool:
        # null available = unknown; treat as purchasable, let the API decide.
        return self.available is None or self.available > 0


# ===========================================================================
# Global sourcing settings (singleton)
# ===========================================================================

class SourcingSettings(models.Model):
    """One-row settings controlling pricing defaults & fulfilment behaviour."""

    prefer_own_stock = models.BooleanField(
        default=True,
        help_text="If own stock exists, deliver from it before hitting bots.",
    )
    usd_to_pkr_rate = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal("280.0000"),
        help_text="Used to convert a bot's USD cost into a PKR selling price.",
    )
    default_retail_margin_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("30.00"),
        help_text="Default markup for normal (retail) customers.",
    )
    default_reseller_margin_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("15.00"),
        help_text="Default markup for reseller-panel customers.",
    )
    reseller_min_deposit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("2000.00"),
        help_text="Minimum wallet deposit a reseller needs to activate the panel.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sourcing Settings"
        verbose_name_plural = "Sourcing Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return "Sourcing Settings"

    @classmethod
    def load(cls) -> "SourcingSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ===========================================================================
# Local product <-> supplier mapping + pricing
# ===========================================================================

class ProductSourcing(models.Model):
    """Per-product sourcing & pricing config (OneToOne with the local Product).

    Keeps the existing `product` app untouched; all reseller/auto-buy config
    lives here.
    """

    product = models.OneToOneField(
        Product, related_name="sourcing", on_delete=models.CASCADE
    )
    auto_match_enabled = models.BooleanField(
        default=True,
        help_text="Let the system auto-link bot products by name. Manual links "
                  "always take priority and are never overwritten.",
    )

    # Frontend visibility — only ticked products appear on each panel.
    show_on_retail = models.BooleanField(
        default=False,
        help_text="Show this product on the public (retail) store.",
    )
    show_on_reseller = models.BooleanField(
        default=False,
        help_text="Show this product on the reseller panel (login required).",
    )

    # Pricing — leave a margin blank to use the global default; set an override
    # to pin an exact PKR price regardless of bot cost.
    retail_margin_percent = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Blank = use global default retail margin.",
    )
    reseller_margin_percent = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Blank = use global default reseller margin.",
    )
    # Optional flat commission (added on top of the percentage), per product.
    retail_commission_flat = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Extra flat PKR added to every retail offer (on top of %).",
    )
    reseller_commission_flat = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Extra flat PKR added to every reseller offer (on top of %).",
    )
    # NOTE: retail_price_override / reseller_price_override are legacy (kept to
    # avoid a destructive migration) and are no longer used — pricing is per-offer.
    retail_price_override = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Legacy, unused.",
    )
    reseller_price_override = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Legacy, unused.",
    )

    class Meta:
        verbose_name = "Product Sourcing"
        verbose_name_plural = "Product Sourcing"

    def __str__(self) -> str:
        return f"Sourcing for {self.product.title}"

    # -- commission (percent) --------------------------------------------

    def retail_pct(self) -> Decimal:
        s = SourcingSettings.load()
        return (self.retail_margin_percent if self.retail_margin_percent is not None
                else s.default_retail_margin_percent)

    def reseller_pct(self) -> Decimal:
        s = SourcingSettings.load()
        return (self.reseller_margin_percent if self.reseller_margin_percent is not None
                else s.default_reseller_margin_percent)

    # -- offers (each enabled link is a user-selectable offer) ------------

    def enabled_links(self) -> list["ProductSourceLink"]:
        links = [
            l for l in self.links.filter(is_enabled=True)
            .select_related("supplier_product", "supplier_product__bot")
            if l.supplier_product
            and l.supplier_product.usd_pricing is not None
            and l.supplier_product.bot.is_active
        ]
        return sorted(links, key=lambda l: l.supplier_product.usd_pricing)

    def price_for(self, buyer_type: str) -> Decimal | None:
        """Lowest offer price (the 'from' price shown on listings)."""
        prices = [p for p in (l.price_for(buyer_type) for l in self.enabled_links())
                  if p is not None]
        return min(prices) if prices else None

    def retail_price(self) -> Decimal | None:
        return self.price_for("retail")

    def reseller_price(self) -> Decimal | None:
        return self.price_for("reseller")

    def has_source(self) -> bool:
        """True if at least one enabled, in-stock offer exists."""
        return any(l.supplier_product.in_stock for l in self.enabled_links())

    def is_visible_for(self, buyer_type: str) -> bool:
        """Show on a panel only if ticked, product active, priced and fulfillable."""
        flag = self.show_on_reseller if buyer_type == "reseller" else self.show_on_retail
        return bool(
            flag
            and self.product.status
            and self.has_source()
            and self.price_for(buyer_type) is not None
        )


class ProductSourceLink(models.Model):
    """Links a local product to one bot's product (its supplier offer)."""

    class MatchType(models.TextChoices):
        AUTO = "auto", "Auto (by name)"
        MANUAL = "manual", "Manual"

    product_sourcing = models.ForeignKey(
        ProductSourcing, related_name="links", on_delete=models.CASCADE
    )
    supplier_product = models.ForeignKey(
        SupplierProduct, related_name="links", on_delete=models.CASCADE
    )
    match_type = models.CharField(
        max_length=10, choices=MatchType.choices, default=MatchType.MANUAL
    )
    is_enabled = models.BooleanField(default=True)
    display_name = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Shown to the customer (bot name is hidden). Blank = 'Plan N'.",
    )
    buy_quantity = models.PositiveIntegerField(
        default=1,
        help_text="Units to buy per 1 unit sold (normal products). Slots ignore this.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("product_sourcing", "supplier_product")
        verbose_name = "Product ↔ Bot link"
        verbose_name_plural = "Product ↔ Bot links"

    def __str__(self) -> str:
        return f"{self.product_sourcing.product.title} → {self.supplier_product}"

    def label(self, index: int = 1) -> str:
        # Show the bot product's own title by default (seller/bot identity stays
        # hidden). Admin can override via display_name; fall back to "Plan N".
        return (self.display_name
                or (self.supplier_product.name if self.supplier_product_id else "")
                or f"Plan {index}")

    def cost_pkr(self) -> Decimal | None:
        usd = self.supplier_product.usd_pricing
        if usd is None:
            return None
        return usd * SourcingSettings.load().usd_to_pkr_rate

    def price_for(self, buyer_type: str) -> Decimal | None:
        """Displayed price for this single offer = cost + commission (% + flat)."""
        cost = self.cost_pkr()
        if cost is None:
            return None
        ps = self.product_sourcing
        if buyer_type == "reseller":
            pct, flat = ps.reseller_pct(), ps.reseller_commission_flat or Decimal("0")
        else:
            pct, flat = ps.retail_pct(), ps.retail_commission_flat or Decimal("0")
        return (cost * (Decimal("1") + pct / Decimal("100")) + flat).quantize(Decimal("0.01"))


# ===========================================================================
# Own stock (pre-loaded credentials)
# ===========================================================================

class StockItem(models.Model):
    """A pre-loaded account the site owns, delivered before falling back to bots."""

    product = models.ForeignKey(
        Product, related_name="stock_items", on_delete=models.CASCADE
    )
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    verify_email = models.CharField(max_length=255, blank=True, default="")
    extra = models.TextField(blank=True, default="")

    is_sold = models.BooleanField(default=False)
    sold_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_sold", "created_at"]
        verbose_name = "Stock Item (own)"
        verbose_name_plural = "Stock Items (own)"

    def __str__(self) -> str:
        state = "SOLD" if self.is_sold else "available"
        return f"{self.product.title} — {self.username} ({state})"


# ===========================================================================
# Orders
# ===========================================================================

class Order(models.Model):
    class BuyerType(models.TextChoices):
        RETAIL = "retail", "Retail"
        RESELLER = "reseller", "Reseller"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed (no stock / all bots failed)"
        NEEDS_REVIEW = "needs_review", "Needs review (ambiguous)"

    class Source(models.TextChoices):
        OWN_STOCK = "own_stock", "Own stock"
        BOT = "bot", "Bot"
        NONE = "", "—"

    idempotency_key = models.CharField(
        max_length=64, unique=True,
        help_text="Prevents the same checkout from creating duplicate orders.",
    )
    user = models.ForeignKey(
        dj_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="sourcing_orders",
    )
    product = models.ForeignKey(
        Product, related_name="sourcing_orders", on_delete=models.PROTECT
    )
    quantity = models.PositiveIntegerField(default=1)
    offer_label = models.CharField(max_length=100, blank=True, default="")
    buyer_type = models.CharField(
        max_length=10, choices=BuyerType.choices, default=BuyerType.RETAIL
    )
    customer_email = models.EmailField(blank=True, default="")
    slot_months = models.PositiveIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.NONE, blank=True
    )
    fulfilled_bot = models.ForeignKey(
        SupplierBot, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="orders",
    )

    sell_amount_pkr = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    cost_amount = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    cost_currency = models.CharField(max_length=8, blank=True, default="")
    canboso_order_code = models.CharField(max_length=64, blank=True, default="")

    error_message = models.CharField(max_length=255, blank=True, default="")
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk} — {self.product.title} [{self.status}]"


class DeliveredAccount(models.Model):
    """A credential handed to the customer for an order (own stock or bot).

    SECURITY NOTE: passwords are stored as plain text here for MVP. Before going
    live, wrap these fields with field-level encryption (e.g. a Fernet-based
    EncryptedCharField) and/or purge after delivery.
    """

    order = models.ForeignKey(
        Order, related_name="delivered_accounts", on_delete=models.CASCADE
    )
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255, blank=True, default="")
    verify_email = models.CharField(max_length=255, blank=True, default="")
    delivered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.username} (order #{self.order_id})"
