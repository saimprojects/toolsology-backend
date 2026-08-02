from django.urls import path

from .views import (
    MeView,
    OrdersListView,
    RegisterView,
    TransactionsListView,
    WalletPurchaseView,
    WalletTopupView,
    DeveloperKeysView,
    DeveloperKeyRevokeView,
    ExternalOrdersView,
    ExternalProductsView,
    ExternalProductOffersView,
    ExternalPurchaseView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="reseller-register"),
    path("me/", MeView.as_view(), name="reseller-me"),
    path("wallet/topup/", WalletTopupView.as_view(), name="reseller-topup"),
    path("wallet/purchase/", WalletPurchaseView.as_view(), name="reseller-purchase"),
    path("wallet/transactions/", TransactionsListView.as_view(), name="reseller-transactions"),
    path("orders/", OrdersListView.as_view(), name="reseller-orders"),
    path("developer/keys/", DeveloperKeysView.as_view(), name="developer-keys"),
    path("developer/keys/<int:pk>/", DeveloperKeyRevokeView.as_view(), name="developer-key-revoke"),
    path("api/v1/products/", ExternalProductsView.as_view(), name="external-products"),
    path("api/v1/products/<slug:slug>/offers/", ExternalProductOffersView.as_view(), name="external-product-offers"),
    path("api/v1/orders/", ExternalOrdersView.as_view(), name="external-orders"),
    path("api/v1/purchase/", ExternalPurchaseView.as_view(), name="external-purchase"),
]
