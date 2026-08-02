from django.contrib import admin, messages
from django.utils import timezone

from .models import Reseller, ResellerApiKey, WalletTransaction


class WalletTransactionInline(admin.TabularInline):
    model = WalletTransaction
    extra = 0
    can_delete = False
    fields = ("kind", "amount", "balance_after", "order", "note", "created_at")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Reseller)
class ResellerAdmin(admin.ModelAdmin):
    list_display = ("user", "wallet_balance", "is_activated", "deposit_required",
                    "wallet_required", "min_deposit_display", "created_at")
    list_filter = ("is_activated", "deposit_required", "wallet_required")
    search_fields = ("user__username", "user__email", "phone")
    list_editable = ("deposit_required", "wallet_required")
    readonly_fields = ("activated_at", "created_at", "updated_at", "min_deposit_display")
    inlines = [WalletTransactionInline]
    actions = ["activate_now", "waive_deposit"]

    @admin.display(description="Min deposit")
    def min_deposit_display(self, obj):
        return obj.min_deposit

    @admin.action(description="Activate selected resellers")
    def activate_now(self, request, queryset):
        n = 0
        for r in queryset:
            if not r.is_activated:
                r.is_activated = True
                r.activated_at = timezone.now()
                r.save(update_fields=["is_activated", "activated_at"])
                n += 1
        self.message_user(request, f"Activated {n} reseller(s).", messages.SUCCESS)

    @admin.action(description="Waive deposit requirement (allow without fee)")
    def waive_deposit(self, request, queryset):
        queryset.update(deposit_required=False)
        self.message_user(request, "Deposit requirement waived for selected.",
                          messages.SUCCESS)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("reseller", "kind", "amount", "balance_after", "order",
                    "created_at")
    list_filter = ("kind",)
    search_fields = ("reseller__user__username", "note")
    readonly_fields = ("reseller", "kind", "amount", "balance_after", "order",
                       "sms", "note", "created_at")


@admin.register(ResellerApiKey)
class ResellerApiKeyAdmin(admin.ModelAdmin):
    list_display = ("reseller", "name", "prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("reseller__user__username", "name", "prefix")
    readonly_fields = ("key_hash", "prefix", "last_used_at", "created_at")

    def has_add_permission(self, request):
        return False
