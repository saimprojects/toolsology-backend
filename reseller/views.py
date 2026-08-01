from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from payments.serializers import OrderResultSerializer
from product.models import Product
from sourcing.models import Order

from .models import WalletTransaction
from .serializers import (
    RegisterSerializer,
    ResellerMeSerializer,
    ResellerOrderSerializer,
    TopupSerializer,
    WalletPurchaseSerializer,
    WalletTransactionSerializer,
)
from .services import (
    WalletError,
    get_or_create_reseller,
    purchase_from_wallet,
    topup_via_trx,
)


class RegisterView(APIView):
    """Self-signup. Creates a pending reseller (activates after deposit)."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "reseller": ResellerMeSerializer(user.reseller).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reseller = get_or_create_reseller(request.user)
        return Response(ResellerMeSerializer(reseller).data)


class WalletTopupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = TopupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reseller = get_or_create_reseller(request.user)
        try:
            txn = topup_via_trx(reseller, ser.validated_data["trx_id"])
        except WalletError as exc:
            return Response({"code": exc.code, "detail": exc.message},
                            status=status.HTTP_400_BAD_REQUEST)
        reseller.refresh_from_db()
        return Response(
            {
                "transaction": WalletTransactionSerializer(txn).data,
                "reseller": ResellerMeSerializer(reseller).data,
            }
        )


class WalletPurchaseView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = WalletPurchaseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        reseller = get_or_create_reseller(request.user)
        product = get_object_or_404(Product, pk=v["product_id"], status=True)
        try:
            order = purchase_from_wallet(
                reseller,
                product=product,
                quantity=v["quantity"],
                idempotency_key=v["idempotency_key"],
                customer_email=v.get("customer_email", ""),
                slot_months=v.get("slot_months"),
            )
        except WalletError as exc:
            return Response({"code": exc.code, "detail": exc.message},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(OrderResultSerializer(order).data)


class TransactionsListView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        reseller = get_or_create_reseller(self.request.user)
        return reseller.transactions.all()


class OrdersListView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ResellerOrderSerializer

    def get_queryset(self):
        return (Order.objects.filter(user=self.request.user)
                .select_related("product")
                .prefetch_related("delivered_accounts"))
