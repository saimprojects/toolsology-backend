from django.urls import path

from .views import (
    PaymentMethodListView,
    ResellerCheckoutView,
    RetailCheckoutView,
    SmsWebhookView,
)

urlpatterns = [
    path("methods/", PaymentMethodListView.as_view(), name="payment-methods"),
    path("sms-webhook/", SmsWebhookView.as_view(), name="sms-webhook"),
    path("checkout/retail/", RetailCheckoutView.as_view(), name="checkout-retail"),
    path("checkout/reseller/", ResellerCheckoutView.as_view(), name="checkout-reseller"),
]
