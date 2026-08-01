from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from sourcing.models import Order

from .serializers import (
    CustomerMeSerializer,
    CustomerOrderSerializer,
    CustomerRegisterSerializer,
)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = CustomerRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": CustomerMeSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(CustomerMeSerializer(request.user).data)


class OrdersView(ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CustomerOrderSerializer
    pagination_class = None

    def get_queryset(self):
        return (Order.objects.filter(user=self.request.user, buyer_type="retail")
                .select_related("product")
                .prefetch_related("delivered_accounts"))
