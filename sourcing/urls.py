from django.urls import path

from .views import RetailProductList, ResellerProductList

urlpatterns = [
    # Public storefront
    path("retail/products/", RetailProductList.as_view(), name="retail-products"),
    # Reseller panel (JWT auth required)
    path("reseller/products/", ResellerProductList.as_view(), name="reseller-products"),
]
