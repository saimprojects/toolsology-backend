from django.urls import path

from .views import (
    MeView,
    OrdersListView,
    RegisterView,
    TransactionsListView,
    WalletPurchaseView,
    WalletTopupView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="reseller-register"),
    path("me/", MeView.as_view(), name="reseller-me"),
    path("wallet/topup/", WalletTopupView.as_view(), name="reseller-topup"),
    path("wallet/purchase/", WalletPurchaseView.as_view(), name="reseller-purchase"),
    path("wallet/transactions/", TransactionsListView.as_view(), name="reseller-transactions"),
    path("orders/", OrdersListView.as_view(), name="reseller-orders"),
]
