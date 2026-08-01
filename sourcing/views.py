"""Storefront + reseller-panel product listings.

Only products the admin has explicitly ticked (show_on_retail / show_on_reseller)
that are active, priced and fulfillable appear here. The cheapest bot is chosen
internally at purchase time — the frontend only ever sees one final price.
"""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.generics import ListAPIView

from .models import ProductSourcing
from .serializers import PublicSourcingProductSerializer


class _BaseSourcingList(ListAPIView):
    serializer_class = PublicSourcingProductSerializer
    audience = "retail"
    visibility_field = "show_on_retail"

    def get_queryset(self):
        qs = (
            ProductSourcing.objects
            .filter(product__status=True, **{self.visibility_field: True})
            .select_related("product")
            .prefetch_related(
                "product__images",
                "product__categories",
                "product__stock_items",
                "links__supplier_product__bot",
            )
        )
        # Keep only rows that are actually sellable for this audience.
        return [s for s in qs if s.is_visible_for(self.audience)]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["audience"] = self.audience
        return ctx


class RetailProductList(_BaseSourcingList):
    """Public storefront — no login required."""
    permission_classes = [permissions.AllowAny]
    audience = "retail"
    visibility_field = "show_on_retail"


class ResellerProductList(_BaseSourcingList):
    """Reseller panel — login (JWT) required, reseller pricing."""
    permission_classes = [permissions.IsAuthenticated]
    audience = "reseller"
    visibility_field = "show_on_reseller"
