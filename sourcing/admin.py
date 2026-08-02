from django import forms
from django.contrib import admin, messages
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from product.models import Product

from .models import (
    DeliveredAccount,
    Order,
    ProductSourceLink,
    ProductSourcing,
    SourcingSettings,
    StockField,
    StockItem,
    StockOffer,
    SupplierBot,
    SupplierProduct,
)
from .services import auto_match, sync_bot


class SupplierProductChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        stock = "Unlimited" if obj.available is None else str(obj.available)
        price = f"${obj.usd_pricing}" if obj.usd_pricing is not None else "No price"
        # Keep a stable marker so our admin search can match only the product
        # title while still displaying useful supplier metadata.
        return f"{obj.name} [Bot: {obj.bot.name} | {price} | Stock: {stock}]"


class ProductSourcingAdminForm(forms.ModelForm):
    selected_bot_products = SupplierProductChoiceField(
        queryset=SupplierProduct.objects.none(),
        required=False,
        label="Available and selected bot products",
        widget=FilteredSelectMultiple("bot products", is_stacked=False),
        help_text=(
            "Double-click a product (or use the arrows) to move it to Selected. "
            "Save this page and it will appear as an editable row in Product ↔ Bot Links."
        ),
    )

    class Meta:
        model = ProductSourcing
        fields = "__all__"

    class Media:
        js = ("sourcing/js/product_selector_filter.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected_bot_products"].queryset = (
            SupplierProduct.objects.filter(bot__is_active=True)
            .select_related("bot")
            .order_by("bot__priority", "bot__name", "name", "usd_pricing")
        )
        if self.instance and self.instance.pk:
            self.initial["selected_bot_products"] = list(
                self.instance.links.values_list("supplier_product_id", flat=True)
            )


class SupplierProductInline(admin.TabularInline):
    model = SupplierProduct
    extra = 0
    can_delete = False
    fields = ("name", "remote_id", "wallet_pricing", "wallet_currency",
              "usd_pricing", "available", "is_slot", "last_synced")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupplierBot)
class SupplierBotAdmin(admin.ModelAdmin):
    list_display = ("name", "bot_source", "masked_key", "is_active", "priority",
                    "wallet_currency", "last_balance_text", "product_count",
                    "last_synced", "sync_status")
    list_filter = ("is_active", "bot_source")
    search_fields = ("name",)
    list_editable = ("is_active", "priority")
    inlines = [SupplierProductInline]
    actions = ["sync_selected_bots"]

    fieldsets = (
        (None, {"fields": ("name", "bot_source", "api_key", "base_url",
                           "is_active", "priority")}),
        ("Cached wallet (read-only)", {
            "fields": ("wallet_currency", "last_balance", "last_balance_text",
                       "last_synced", "last_sync_error"),
        }),
    )
    readonly_fields = ("wallet_currency", "last_balance", "last_balance_text",
                       "last_synced", "last_sync_error")

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()

    @admin.display(description="Last sync")
    def sync_status(self, obj):
        if obj.last_sync_error:
            return "⚠ " + obj.last_sync_error
        if not obj.last_synced:
            return "Never synced"
        return "OK"

    @admin.action(description="Sync catalogue & balance from Canboso")
    def sync_selected_bots(self, request, queryset):
        ok = errs = 0
        for bot in queryset:
            result = sync_bot(bot)
            if result["error"]:
                errs += 1
                self.message_user(
                    request, f"{bot.name}: {result['error']}", level=messages.ERROR
                )
            else:
                ok += 1
                self.message_user(
                    request,
                    f"{bot.name}: synced {result['synced']} products.",
                    level=messages.SUCCESS,
                )
        self.message_user(
            request, f"Done. {ok} bot(s) OK, {errs} with errors.",
            level=messages.INFO,
        )


@admin.register(SupplierProduct)
class SupplierProductAdmin(admin.ModelAdmin):
    list_display = ("name", "bot", "usd_pricing", "wallet_pricing",
                    "wallet_currency", "available", "is_slot", "last_synced")
    list_filter = ("bot", "is_slot", "wallet_currency")
    search_fields = ("name", "remote_id")
    readonly_fields = ("bot", "remote_id", "name", "name_raw", "wallet_currency",
                       "wallet_pricing", "usd_pricing", "available", "is_slot",
                       "slot_durations", "raw", "last_synced")

    def has_add_permission(self, request):
        return False


# ===========================================================================
# Global settings (singleton)
# ===========================================================================

@admin.register(SourcingSettings)
class SourcingSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "prefer_own_stock", "usd_to_pkr_rate",
                    "default_retail_margin_percent",
                    "default_reseller_margin_percent", "updated_at")

    def has_add_permission(self, request):
        return not SourcingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# ===========================================================================
# Product sourcing + pricing
# ===========================================================================

class ProductSourceLinkInline(admin.TabularInline):
    model = ProductSourceLink
    extra = 0
    autocomplete_fields = ("supplier_product",)
    fields = ("supplier_product", "display_name", "short_description", "is_enabled",
              "buy_quantity", "sp_usd", "sp_stock", "retail_price", "reseller_price")
    readonly_fields = ("sp_usd", "sp_stock", "retail_price", "reseller_price")

    @admin.display(description="USD cost")
    def sp_usd(self, obj):
        return obj.supplier_product.usd_pricing if obj.supplier_product_id else "-"

    @admin.display(description="Stock")
    def sp_stock(self, obj):
        return obj.supplier_product.available if obj.supplier_product_id else "-"

    @admin.display(description="Retail PKR")
    def retail_price(self, obj):
        return obj.price_for("retail") if obj.pk else "-"

    @admin.display(description="Reseller PKR")
    def reseller_price(self, obj):
        return obj.price_for("reseller") if obj.pk else "-"


@admin.register(ProductSourcing)
class ProductSourcingAdmin(admin.ModelAdmin):
    form = ProductSourcingAdminForm
    list_display = ("product", "show_on_retail", "show_on_reseller",
                    "linked_bots", "retail_price_display", "reseller_price_display")
    list_editable = ("show_on_retail", "show_on_reseller")
    list_filter = ("show_on_retail", "show_on_reseller", "auto_match_enabled")
    search_fields = ("product__title",)
    autocomplete_fields = ("product",)
    inlines = [ProductSourceLinkInline]
    actions = ["run_auto_match", "show_on_both", "hide_from_both"]
    fieldsets = (
        (None, {"fields": ("product", "auto_match_enabled",
                           "show_on_retail", "show_on_reseller")}),
        ("Choose bot products", {
            "fields": ("selected_bot_products",),
            "description": (
                "Choose the exact supplier offers for this store product. "
                "Double-click to move products between Available and Selected."
            ),
        }),
        ("Commission (added on top of bot cost)", {
            "fields": ("retail_margin_percent", "retail_commission_flat",
                       "reseller_margin_percent", "reseller_commission_flat"),
            "description": "Percent + optional flat PKR. Blank percent = global "
                           "default. Applies to every offer of this product.",
        }),
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        selected_ids = set(
            form.cleaned_data.get("selected_bot_products", []).values_list("pk", flat=True)
        )
        existing_ids = set(
            form.instance.links.values_list("supplier_product_id", flat=True)
        )

        # Existing selected rows keep their custom display name, description,
        # quantity and enabled state. Only genuinely new/removed choices change.
        form.instance.links.filter(
            supplier_product__bot__is_active=True,
            supplier_product_id__in=existing_ids - selected_ids,
        ).delete()
        ProductSourceLink.objects.bulk_create([
            ProductSourceLink(
                product_sourcing=form.instance,
                supplier_product_id=product_id,
                match_type=ProductSourceLink.MatchType.MANUAL,
            )
            for product_id in selected_ids - existing_ids
        ], ignore_conflicts=True)

    @admin.action(description="Show on retail + reseller")
    def show_on_both(self, request, queryset):
        queryset.update(show_on_retail=True, show_on_reseller=True)
        self.message_user(request, "Selected products are now visible on both panels.")

    @admin.action(description="Hide from both panels")
    def hide_from_both(self, request, queryset):
        queryset.update(show_on_retail=False, show_on_reseller=False)
        self.message_user(request, "Selected products are now hidden.")

    @admin.display(description="Linked bots")
    def linked_bots(self, obj):
        return obj.links.filter(is_enabled=True).count()

    @admin.display(description="Retail from (PKR)")
    def retail_price_display(self, obj):
        return obj.retail_price()

    @admin.display(description="Reseller (PKR)")
    def reseller_price_display(self, obj):
        return obj.reseller_price()

    @admin.action(description="Auto-match bot products by name")
    def run_auto_match(self, request, queryset):
        total = sum(auto_match(s) for s in queryset)
        self.message_user(
            request, f"Created {total} new auto-link(s).", level=messages.SUCCESS
        )


# ===========================================================================
# Own stock
# ===========================================================================

@admin.register(StockOffer)
class StockOfferAdmin(admin.ModelAdmin):
    list_display = ("product", "display_name", "retail_price", "reseller_price",
                    "available", "is_enabled", "show_on_retail", "show_on_reseller")
    list_editable = ("retail_price", "reseller_price", "is_enabled",
                     "show_on_retail", "show_on_reseller")
    list_filter = ("is_enabled", "show_on_retail", "show_on_reseller")
    search_fields = ("product__title", "display_name")
    autocomplete_fields = ("product",)

    @admin.display(description="Stock available")
    def available(self, obj):
        return obj.available_count()


class StockFieldInline(admin.TabularInline):
    model = StockField
    extra = 3
    fields = ("name", "value", "order")


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("product", "account_summary", "is_sold", "created_at")
    list_filter = ("is_sold", "product")
    search_fields = ("product__title", "fields__value", "fields__name")
    inlines = [StockFieldInline]
    fields = ("product", "is_sold")
    change_list_template = "admin/sourcing/stockitem/change_list.html"

    @admin.display(description="Account")
    def account_summary(self, obj):
        return obj.summary()

    # -- Bulk add ---------------------------------------------------------

    def get_urls(self):
        custom = [
            path("bulk-add/", self.admin_site.admin_view(self.bulk_add_view),
                 name="sourcing_stockitem_bulk_add"),
        ]
        return custom + super().get_urls()

    def bulk_add_view(self, request):
        if request.method == "POST":
            product = Product.objects.filter(id=request.POST.get("product")).first()
            names = [n.strip() for n in request.POST.get("field_names", "").split(",")
                     if n.strip()]
            rows = request.POST.get("rows", "")
            if not (product and names and rows.strip()):
                self.message_user(
                    request, "Please choose a product, field names and paste rows.",
                    level=messages.ERROR)
            else:
                count = 0
                for line in rows.splitlines():
                    if not line.strip():
                        continue
                    parts = line.split("\t") if "\t" in line else line.split(",")
                    parts = [p.strip() for p in parts]
                    item = StockItem.objects.create(product=product)
                    for i, name in enumerate(names):
                        StockField.objects.create(
                            stock_item=item, name=name,
                            value=parts[i] if i < len(parts) else "", order=i)
                    count += 1
                self.message_user(request, f"Added {count} stock item(s).",
                                  level=messages.SUCCESS)
                return redirect("..")

        context = {
            **self.admin_site.each_context(request),
            "title": "Bulk add stock",
            "opts": self.model._meta,
            "products": Product.objects.all().order_by("title"),
        }
        return TemplateResponse(
            request, "admin/sourcing/stockitem/bulk_add.html", context)


# ===========================================================================
# Orders
# ===========================================================================

class DeliveredAccountInline(admin.TabularInline):
    model = DeliveredAccount
    extra = 0
    readonly_fields = ("username", "password", "verify_email", "delivered_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "buyer_type", "quantity", "status",
                    "source", "fulfilled_bot", "sell_amount_pkr", "promo_code",
                    "canboso_order_code", "created_at")
    list_filter = ("status", "source", "buyer_type", "fulfilled_bot")
    search_fields = ("id", "product__title", "customer_email",
                     "canboso_order_code", "idempotency_key")
    date_hierarchy = "created_at"
    inlines = [DeliveredAccountInline]
    readonly_fields = ("idempotency_key", "user", "product", "quantity",
                       "buyer_type", "customer_email", "slot_months", "promo_code", "source",
                       "fulfilled_bot", "sell_amount_pkr", "cost_amount",
                       "cost_currency", "canboso_order_code", "error_message",
                       "raw_response", "created_at", "updated_at")
