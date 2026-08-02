from __future__ import annotations

from rest_framework import serializers

from sourcing.models import DeliveredAccount, Order

from .models import PaymentMethod


class PaymentMethodSerializer(serializers.ModelSerializer):
    icon = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = ["id", "name", "account_title", "account_number",
                  "icon", "instructions"]

    def get_icon(self, obj):
        return obj.icon.url if obj.icon else None


class CheckoutSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    offer_id = serializers.CharField(max_length=32)
    quantity = serializers.IntegerField(min_value=1, default=1)
    trx_id = serializers.CharField(max_length=160)
    payment_type = serializers.ChoiceField(
        choices=["local", "binance", "binance_id"], default="local", required=False
    )
    idempotency_key = serializers.CharField(max_length=64)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    slot_months = serializers.IntegerField(required=False, allow_null=True, default=None)


class DeliveredAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveredAccount
        fields = ["username", "password", "verify_email", "details", "delivered_at"]


class OrderResultSerializer(serializers.ModelSerializer):
    delivered_accounts = DeliveredAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "status", "source", "quantity", "sell_amount_pkr",
                  "canboso_order_code", "error_message", "delivered_accounts"]
