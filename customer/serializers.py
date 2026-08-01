from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import serializers

from payments.serializers import DeliveredAccountSerializer
from sourcing.models import Order

User = get_user_model()


class CustomerRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def create(self, validated):
        return User.objects.create_user(
            username=validated["username"],
            email=validated.get("email", ""),
            password=validated["password"],
        )


class CustomerMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class CustomerOrderSerializer(serializers.ModelSerializer):
    product_title = serializers.CharField(source="product.title", read_only=True)
    delivered_accounts = DeliveredAccountSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "product_title", "quantity", "status", "sell_amount_pkr",
                  "canboso_order_code", "created_at", "delivered_accounts"]
