from django.urls import path

from .views import MeView, OrdersView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="customer-register"),
    path("me/", MeView.as_view(), name="customer-me"),
    path("orders/", OrdersView.as_view(), name="customer-orders"),
]
