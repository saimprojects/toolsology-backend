from django.contrib import admin
from django.utils.html import format_html

from .models import IncomingSms, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "account_title", "account_number", "icon_preview",
                    "is_active", "ordering")
    list_editable = ("is_active", "ordering")
    search_fields = ("name", "account_title", "account_number")

    @admin.display(description="Icon")
    def icon_preview(self, obj):
        if obj.icon:
            return format_html('<img src="{}" style="height:28px;" />', obj.icon.url)
        return "—"


@admin.register(IncomingSms)
class IncomingSmsAdmin(admin.ModelAdmin):
    list_display = ("trx_id", "amount", "sender", "method", "is_consumed",
                    "consumed_by_order", "received_at")
    list_filter = ("is_consumed", "method", "sender")
    search_fields = ("trx_id", "raw_message", "sender")
    readonly_fields = ("received_at", "consumed_at", "consumed_by_order")
    fields = ("raw_message", "sender", "trx_id", "amount", "method",
              "is_consumed", "consumed_at", "consumed_by_order", "received_at")

    def has_add_permission(self, request):
        # SMS arrive via the webhook; manual add is allowed for reconciliation.
        return True
