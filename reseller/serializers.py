from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from sourcing.models import Order
from payments.serializers import DeliveredAccountSerializer

from .models import Reseller, WalletTransaction

User = get_user_model()


class ResellerOrderSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    delivered_accounts = DeliveredAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "product_title", "quantity", "status", "source",
                  "sell_amount_pkr", "canboso_order_code", "error_message",
                  "created_at", "delivered_accounts"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)
    phone = serializers.CharField(max_length=32)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def create(self, validated):
        user = User.objects.create_user(
            username=validated["username"],
            email=validated.get("email", ""),
            password=validated["password"],
        )
        Reseller.objects.create(user=user, phone=validated.get("phone", ""))
        return user


class ResellerMeSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    min_deposit = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    can_operate = serializers.BooleanField(read_only=True)

    class Meta:
        model = Reseller
        fields = ["username", "wallet_balance", "is_activated", "deposit_required",
                  "wallet_required", "min_deposit", "can_operate", "phone"]


class TopupSerializer(serializers.Serializer):
    trx_id = serializers.CharField(max_length=160)
    payment_type = serializers.ChoiceField(
        choices=["local", "binance", "binance_id"], default="local", required=False
    )


class WalletPurchaseSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    offer_id = serializers.CharField(max_length=32)
    quantity = serializers.IntegerField(min_value=1, default=1)
    idempotency_key = serializers.CharField(max_length=64)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    slot_months = serializers.IntegerField(required=False, allow_null=True, default=None)


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ["id", "kind", "amount", "balance_after", "note", "created_at"]
