from django.contrib import admin, messages

from .models import (
    DeliveredAccount,
    Order,
    ProductSourceLink,
    ProductSourcing,
    SourcingSettings,
    StockItem,
    SupplierBot,
    SupplierProduct,
)
from .services import auto_match, sync_bot


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
        return "⚠ " + obj.last_sync_error if obj.last_sync_error else "OK"

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
    fields = ("supplier_product", "match_type", "is_enabled", "buy_quantity",
              "sp_usd", "sp_stock")
    readonly_fields = ("sp_usd", "sp_stock")

    @admin.display(description="USD cost")
    def sp_usd(self, obj):
        return obj.supplier_product.usd_pricing if obj.supplier_product_id else "-"

    @admin.display(description="Stock")
    def sp_stock(self, obj):
        return obj.supplier_product.available if obj.supplier_product_id else "-"


@admin.register(ProductSourcing)
class ProductSourcingAdmin(admin.ModelAdmin):
    list_display = ("product", "auto_match_enabled", "linked_bots",
                    "cost_pkr_display", "retail_price_display",
                    "reseller_price_display")
    list_filter = ("auto_match_enabled",)
    search_fields = ("product__title",)
    autocomplete_fields = ("product",)
    inlines = [ProductSourceLinkInline]
    actions = ["run_auto_match"]

    @admin.display(description="Linked bots")
    def linked_bots(self, obj):
        return obj.links.filter(is_enabled=True).count()

    @admin.display(description="Cost (PKR)")
    def cost_pkr_display(self, obj):
        return obj.cost_pkr()

    @admin.display(description="Retail (PKR)")
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

@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("product", "username", "is_sold", "sold_at", "created_at")
    list_filter = ("is_sold", "product")
    search_fields = ("product__title", "username")
    readonly_fields = ("sold_at", "created_at")


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
                    "source", "fulfilled_bot", "sell_amount_pkr",
                    "canboso_order_code", "created_at")
    list_filter = ("status", "source", "buyer_type", "fulfilled_bot")
    search_fields = ("id", "product__title", "customer_email",
                     "canboso_order_code", "idempotency_key")
    date_hierarchy = "created_at"
    inlines = [DeliveredAccountInline]
    readonly_fields = ("idempotency_key", "user", "product", "quantity",
                       "buyer_type", "customer_email", "slot_months", "source",
                       "fulfilled_bot", "sell_amount_pkr", "cost_amount",
                       "cost_currency", "canboso_order_code", "error_message",
                       "raw_response", "created_at", "updated_at")
