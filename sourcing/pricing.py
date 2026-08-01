"""Shared offer-pricing helper used by listings and the product serializer."""

from __future__ import annotations


def offer_summary(product, audience: str):
    """Return (from_price, in_stock) across a product's bot + own-stock offers.

    from_price = lowest price of any visible, priced offer for this audience.
    in_stock   = True if any of those offers is currently in stock.
    """
    from .models import ProductSourcing  # local import avoids load-order issues

    vf = "show_on_reseller" if audience == "reseller" else "show_on_retail"
    prices, in_stock = [], False

    try:
        sourcing = product.sourcing
    except ProductSourcing.DoesNotExist:
        sourcing = None

    if sourcing and getattr(sourcing, vf):
        for link in sourcing.enabled_links():
            p = link.price_for(audience)
            if p is not None:
                prices.append(p)
                if link.supplier_product.in_stock:
                    in_stock = True

    for so in product.stock_offers.filter(is_enabled=True, **{vf: True}):
        prices.append(so.price_for(audience))
        if so.in_stock():
            in_stock = True

    return (min(prices) if prices else None), in_stock
