from django.urls import path

from .views import (
    BinanceConfigView,
    CurrencyConfigView,
    PaymentMethodListView,
    PromoPreviewView,
    ResellerCheckoutView,
    RetailCheckoutView,
    SmsWebhookView,
)

urlpatterns = [
    path("methods/", PaymentMethodListView.as_view(), name="payment-methods"),
    path("binance/config/", BinanceConfigView.as_view(), name="binance-config"),
    path("currency/config/", CurrencyConfigView.as_view(), name="currency-config"),
    path("promo/preview/", PromoPreviewView.as_view(), name="promo-preview"),
    path("sms-webhook/", SmsWebhookView.as_view(), name="sms-webhook"),
    path("checkout/retail/", RetailCheckoutView.as_view(), name="checkout-retail"),
    path("checkout/reseller/", ResellerCheckoutView.as_view(), name="checkout-reseller"),
]
