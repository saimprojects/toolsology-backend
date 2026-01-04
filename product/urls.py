
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ProductViewSet,
    ReviewViewSet,
    WhatsAppSettingsPublicView,
    ProductPlanViewSet,

)

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"reviews", ReviewViewSet, basename="review")
router.register(r"plans", ProductPlanViewSet, basename="plan")


urlpatterns = [
    *router.urls,  # ✅ all router-based endpoints
    path("whatsapp/", WhatsAppSettingsPublicView.as_view(), name="whatsapp-settings"),
]
