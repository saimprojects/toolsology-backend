from __future__ import annotations

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from product.models import Product

from .models import PaymentMethod
from .serializers import (
    CheckoutSerializer,
    OrderResultSerializer,
    PaymentMethodSerializer,
)
from .services import PaymentError, store_incoming_sms, verify_and_fulfill
from .binance import currency_config, public_config


class PaymentMethodListView(ListAPIView):
    """Public — where customers should send money."""
    permission_classes = [permissions.AllowAny]
    serializer_class = PaymentMethodSerializer
    queryset = PaymentMethod.objects.filter(is_active=True)
    pagination_class = None


class BinanceConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(public_config())


class CurrencyConfigView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(currency_config())


class SmsWebhookView(APIView):
    """Receives forwarded payment SMS from the Android gateway app.

    SECURITY: protected by a shared secret. The forwarder must include the token
    either as `?token=...` or header `X-Webhook-Token`. Without a correct token
    the request is rejected, so nobody can inject fake payments.
    """
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        expected = getattr(settings, "SMS_WEBHOOK_TOKEN", "") or ""
        provided = (
            request.query_params.get("token")
            or request.headers.get("X-Webhook-Token")
            or ""
        )
        if not expected or provided != expected:
            return Response({"detail": "Invalid token."},
                            status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}
        message = (data.get("message") or data.get("text")
                   or data.get("sms") or data.get("content") or "")
        sender = (data.get("from") or data.get("sender")
                  or data.get("number") or "")

        if not message:
            return Response({"detail": "No message content."},
                            status=status.HTTP_400_BAD_REQUEST)

        sms = store_incoming_sms(raw_message=message, sender=sender)
        return Response(
            {"status": "received", "trx_id": sms.trx_id, "amount": sms.amount},
            status=status.HTTP_200_OK,
        )


class _BaseCheckoutView(APIView):
    buyer_type = "retail"

    def post(self, request):
        ser = CheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        product = get_object_or_404(Product, pk=v["product_id"], status=True)
        try:
            order = verify_and_fulfill(
                product=product,
                offer_id=v["offer_id"],
                quantity=v["quantity"],
                buyer_type=self.buyer_type,
                trx_id=v["trx_id"],
                idempotency_key=v["idempotency_key"],
                customer_email=v.get("customer_email", ""),
                slot_months=v.get("slot_months"),
                user=request.user if request.user.is_authenticated else None,
                payment_type=v.get("payment_type", "local"),
            )
        except PaymentError as exc:
            return Response({"code": exc.code, "detail": exc.message},
                            status=status.HTTP_400_BAD_REQUEST)

        return Response(OrderResultSerializer(order).data, status=status.HTTP_200_OK)


class RetailCheckoutView(_BaseCheckoutView):
    permission_classes = [permissions.AllowAny]
    buyer_type = "retail"


class ResellerCheckoutView(_BaseCheckoutView):
    permission_classes = [permissions.IsAuthenticated]
    buyer_type = "reseller"
