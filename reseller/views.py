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

from .models import ResellerApiKey, WalletTransaction
from .authentication import ResellerApiKeyAuthentication
from .permissions import ActiveResellerPermission
from sourcing.models import ProductSourcing, StockOffer
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
    topup_via_binance,
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
        was_active = reseller.is_activated
        reseller.refresh_activation()
        if reseller.is_activated != was_active:
            reseller.save(update_fields=["is_activated", "activated_at"])
        return Response(ResellerMeSerializer(reseller).data)


class WalletTopupView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = TopupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        reseller = get_or_create_reseller(request.user)
        try:
            if ser.validated_data.get("payment_type") in {"binance", "binance_id"}:
                txn = topup_via_binance(
                    reseller, ser.validated_data["trx_id"],
                    via_pay_id=ser.validated_data.get("payment_type") == "binance_id",
                )
            else:
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
    permission_classes = [permissions.IsAuthenticated, ActiveResellerPermission]

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
                offer_id=v["offer_id"],
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
    permission_classes = [permissions.IsAuthenticated, ActiveResellerPermission]
    serializer_class = ResellerOrderSerializer

    def get_queryset(self):
        return (Order.objects.filter(user=self.request.user)
                .select_related("product")
                .prefetch_related("delivered_accounts"))


class DeveloperKeysView(APIView):
    permission_classes = [permissions.IsAuthenticated, ActiveResellerPermission]

    def get(self, request):
        reseller = get_or_create_reseller(request.user)
        return Response([{
            "id": key.id, "name": key.name, "prefix": key.prefix,
            "is_active": key.is_active, "created_at": key.created_at,
            "last_used_at": key.last_used_at,
        } for key in reseller.api_keys.all()])

    def post(self, request):
        reseller = get_or_create_reseller(request.user)
        if not reseller.can_operate:
            return Response({"detail": "Activate your reseller account first."}, status=400)
        active_count = reseller.api_keys.filter(is_active=True).count()
        if active_count >= 3:
            return Response({"detail": "Maximum 3 active API keys allowed."}, status=400)
        key, raw = ResellerApiKey.issue(reseller, str(request.data.get("name", "Primary"))[:80])
        return Response({"id": key.id, "name": key.name, "prefix": key.prefix, "api_key": raw}, status=201)


class DeveloperKeyRevokeView(APIView):
    permission_classes = [permissions.IsAuthenticated, ActiveResellerPermission]

    def delete(self, request, pk):
        reseller = get_or_create_reseller(request.user)
        key = get_object_or_404(ResellerApiKey, pk=pk, reseller=reseller)
        key.is_active = False
        key.save(update_fields=["is_active"])
        return Response(status=204)


class _ExternalApiView(APIView):
    authentication_classes = [ResellerApiKeyAuthentication]
    permission_classes = [permissions.IsAuthenticated, ActiveResellerPermission]


class ExternalProductsView(_ExternalApiView):
    def get(self, request):
        products = Product.objects.filter(status=True).prefetch_related("images", "stock_offers")
        data = []
        for product in products:
            prices, in_stock = [], False
            sourcing = ProductSourcing.objects.filter(product=product, show_on_reseller=True).first()
            if sourcing:
                for link in sourcing.enabled_links():
                    price = link.price_for("reseller")
                    if price is not None:
                        prices.append(price)
                        in_stock = in_stock or link.supplier_product.in_stock
            for offer in product.stock_offers.filter(is_enabled=True, show_on_reseller=True):
                prices.append(offer.price_for("reseller"))
                in_stock = in_stock or offer.in_stock()
            if not prices:
                continue
            data.append({"id": product.id, "slug": product.slug, "name": product.title,
                         "price_pkr": str(min(prices)), "in_stock": in_stock})
        return Response({"data": data})


class ExternalProductOffersView(_ExternalApiView):
    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug, status=True)
        offers = []
        sourcing = ProductSourcing.objects.filter(product=product, show_on_reseller=True).first()
        if sourcing:
            for index, link in enumerate(sourcing.enabled_links(), start=1):
                price = link.price_for("reseller")
                if price is not None:
                    offers.append({"offer_id": f"bot-{link.id}", "label": link.label(index),
                                   "description": link.short_description, "price_pkr": str(price),
                                   "in_stock": link.supplier_product.in_stock,
                                   "is_slot": link.supplier_product.is_slot,
                                   "slot_durations": link.supplier_product.slot_durations})
        for offer in StockOffer.objects.filter(product=product, is_enabled=True, show_on_reseller=True):
            offers.append({"offer_id": f"stock-{offer.id}", "label": offer.label(),
                           "description": offer.short_description,
                           "price_pkr": str(offer.price_for("reseller")),
                           "in_stock": offer.in_stock(), "is_slot": False, "slot_durations": []})
        return Response({"product": {"slug": product.slug, "name": product.title}, "data": offers})


class ExternalPurchaseView(_ExternalApiView):
    def post(self, request):
        reseller = request.reseller
        slug = str(request.data.get("product_slug", ""))
        product = get_object_or_404(Product, slug=slug, status=True)
        offer_id = request.data.get("offer_id")
        if not offer_id:
            return Response({"detail": "offer_id is required."}, status=400)
        idem = request.headers.get("Idempotency-Key", "")
        if not idem:
            return Response({"detail": "Idempotency-Key header is required."}, status=400)
        try:
            order = purchase_from_wallet(
                reseller, product=product, offer_id=str(offer_id),
                quantity=max(1, int(request.data.get("quantity", 1))),
                idempotency_key=idem[:64], customer_email=str(request.data.get("customer_email", "")),
            )
        except (WalletError, ValueError) as exc:
            return Response({"detail": getattr(exc, "message", str(exc)), "code": getattr(exc, "code", "bad_request")}, status=400)
        return Response(OrderResultSerializer(order).data)


class ExternalOrdersView(_ExternalApiView):
    def get(self, request):
        orders = (Order.objects.filter(user=request.user).select_related("product")
                  .prefetch_related("delivered_accounts").order_by("-created_at")[:100])
        return Response({"data": [{"id": o.id, "product": o.product.title,
                                    "product_slug": o.product.slug,
                                    "status": o.status, "quantity": o.quantity,
                                    "amount_pkr": str(o.sell_amount_pkr), "created_at": o.created_at,
                                    "error_message": o.error_message,
                                    "delivered_accounts": OrderResultSerializer(o).data["delivered_accounts"]}
                                   for o in orders]})
