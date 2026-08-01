from django.urls import path

from .views import (
    RetailProductList, ResellerProductList,
    RetailProductOffers, ResellerProductOffers,
)

urlpatterns = [
    # Public storefront
    path("retail/products/", RetailProductList.as_view(), name="retail-products"),
    path("retail/products/<int:product_id>/offers/",
         RetailProductOffers.as_view(), name="retail-offers"),
    # Reseller panel (JWT auth required)
    path("reseller/products/", ResellerProductList.as_view(), name="reseller-products"),
    path("reseller/products/<int:product_id>/offers/",
         ResellerProductOffers.as_view(), name="reseller-offers"),
]
