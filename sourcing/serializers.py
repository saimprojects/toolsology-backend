"""Public-facing serializers for the storefront / reseller panel.

These deliberately expose ONLY the final price and availability. Bot identity,
supplier cost and API keys are never serialized to the frontend.
"""

from __future__ import annotations

from rest_framework import serializers


class PublicSourcingProductSerializer(serializers.Serializer):
    """Serialize a ProductSourcing row as a sellable storefront product.

    The audience ('retail' | 'reseller') comes from the view via context and
    decides which price is shown.
    """

    id = serializers.IntegerField(source="product.id")
    title = serializers.CharField(source="product.title")
    description = serializers.CharField(source="product.description")
    categories = serializers.SerializerMethodField()
    main_image = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    is_slot = serializers.SerializerMethodField()
    slot_durations = serializers.SerializerMethodField()

    def _audience(self) -> str:
        return self.context.get("audience", "retail")

    def get_price(self, obj):
        price = obj.price_for(self._audience())
        return str(price) if price is not None else None

    def get_in_stock(self, obj):
        return obj.has_source()

    def get_main_image(self, obj):
        img = (obj.product.images.filter(is_main=True).first()
               or obj.product.images.first())
        return img.image.url if img else None

    def get_images(self, obj):
        return [i.image.url for i in obj.product.images.all()]

    def get_categories(self, obj):
        return [
            {"id": c.id, "name": c.name, "slug": c.slug}
            for c in obj.product.categories.all()
        ]

    def get_is_slot(self, obj):
        link = obj.cheapest_link()
        return bool(link and link.supplier_product.is_slot)

    def get_slot_durations(self, obj):
        link = obj.cheapest_link()
        if link and link.supplier_product.is_slot:
            return link.supplier_product.slot_durations
        return []
