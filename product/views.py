from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets, permissions
from .models import Category, Product, Review, WhatsAppSettings, ProductPlan
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ReviewSerializer,
    WhatsAppSettingsSerializer,
    ProductPlanSerializer,
)


class IsAdminOrReadOnly(permissions.BasePermission):
    """Custom permission to allow only admins to modify data."""

    def has_permission(self, request, view):
        # SAFE_METHODS: GET, HEAD, OPTIONS
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user and request.user.is_staff


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD viewset for categories."""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        # Only return active categories for public GET requests
        qs = super().get_queryset()
        if self.request.method in permissions.SAFE_METHODS:
            qs = qs.filter(status=True)
        return qs


class ProductViewSet(viewsets.ModelViewSet):
    """CRUD viewset for products with public read and admin write access."""
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('images', 'reviews', 'categories')
        # Only return active products for public GET requests
        if self.request.method in permissions.SAFE_METHODS:
            qs = qs.filter(status=True)
        return qs


class ReviewViewSet(viewsets.ModelViewSet):
    """CRUD viewset for reviews. Reviews are managed by admins only."""
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset().select_related('product')
        # For public GET, only show active reviews
        if self.request.method in permissions.SAFE_METHODS:
            qs = qs.filter(status=True)
        return qs
    
class ProductPlanViewSet(viewsets.ModelViewSet):
    queryset = ProductPlan.objects.select_related('product')
    serializer_class = ProductPlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.method in permissions.SAFE_METHODS:
            qs = qs.filter(is_active=True)
        return qs


class WhatsAppSettingsPublicView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        obj, _ = WhatsAppSettings.objects.get_or_create(pk=1, defaults={"whatsapp_number": "+923001234567"})
        return Response(WhatsAppSettingsSerializer(obj).data)
