"""Storefront + reseller-panel product listings.

Only products the admin has explicitly ticked (show_on_retail / show_on_reseller)
that are active, priced and fulfillable appear here. The cheapest bot is chosen
internally at purchase time — the frontend only ever sees one final price.
"""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from product.models import Product

from .models import ProductSourcing, StockOffer


class _BaseSourcingList(APIView):
    """Products visible for an audience — from bot offers AND own-stock offers."""
    audience = "retail"
    visibility_field = "show_on_retail"

    def get(self, request):
        vf = self.visibility_field
        ids = set(
            ProductSourcing.objects
            .filter(product__status=True, **{vf: True})
            .values_list("product_id", flat=True)
        )
        ids.update(
            StockOffer.objects
            .filter(is_enabled=True, product__status=True, **{vf: True})
            .values_list("product_id", flat=True)
        )
        products = (
            Product.objects.filter(id__in=ids, status=True)
            .prefetch_related("images", "categories", "stock_offers")
        )
        out = []
        for product in products:
            price, in_stock = self._summary(product)
            if price is None:
                continue
            out.append(self._serialize(product, price, in_stock))
        return Response(out)

    def _summary(self, product):
        prices, in_stock = [], False
        try:
            sourcing = product.sourcing
        except ProductSourcing.DoesNotExist:
            sourcing = None
        if sourcing and getattr(sourcing, self.visibility_field):
            for link in sourcing.enabled_links():
                p = link.price_for(self.audience)
                if p is not None:
                    prices.append(p)
                    if link.supplier_product.in_stock:
                        in_stock = True
        for so in product.stock_offers.filter(is_enabled=True,
                                               **{self.visibility_field: True}):
            prices.append(so.price_for(self.audience))
            if so.in_stock():
                in_stock = True
        return (min(prices) if prices else None), in_stock

    def _serialize(self, product, price, in_stock):
        img = product.images.filter(is_main=True).first() or product.images.first()
        return {
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "categories": [{"id": c.id, "name": c.name, "slug": c.slug}
                           for c in product.categories.all()],
            "main_image": img.image.url if img else None,
            "images": [i.image.url for i in product.images.all()],
            "price": str(price),
            "in_stock": in_stock,
        }


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


class _BaseOffers(APIView):
    """Offers (attached bot products) for one product — bot names hidden."""
    audience = "retail"
    visibility_field = "show_on_retail"

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, status=True)
        offers = []

        # Bot offers (each attached bot product).
        sourcing = ProductSourcing.objects.filter(product=product).first()
        if sourcing and getattr(sourcing, self.visibility_field):
            for i, link in enumerate(sourcing.enabled_links(), start=1):
                price = link.price_for(self.audience)
                if price is None:
                    continue
                sp = link.supplier_product
                offers.append({
                    "offer_id": f"bot-{link.id}",
                    "label": link.label(i),
                    "price": str(price),
                    "in_stock": sp.in_stock,
                    "available": sp.available,
                    "is_slot": sp.is_slot,
                    "slot_durations": sp.slot_durations,
                })

        # Own-stock offers (fixed price, delivered from your stock).
        for so in StockOffer.objects.filter(
                product=product, is_enabled=True, **{self.visibility_field: True}):
            offers.append({
                "offer_id": f"stock-{so.id}",
                "label": so.label(),
                "price": str(so.price_for(self.audience)),
                "in_stock": so.in_stock(),
                "available": so.available_count(),
                "is_slot": False,
                "slot_durations": [],
            })

        return Response(offers)


class RetailProductOffers(_BaseOffers):
    permission_classes = [permissions.AllowAny]
    audience = "retail"
    visibility_field = "show_on_retail"


class ResellerProductOffers(_BaseOffers):
    permission_classes = [permissions.IsAuthenticated]
    audience = "reseller"
    visibility_field = "show_on_reseller"
