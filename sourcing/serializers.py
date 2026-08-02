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
    slug = serializers.CharField(source="product.slug")
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
        links = obj.enabled_links()
        return bool(links and links[0].supplier_product.is_slot)

    def get_slot_durations(self, obj):
        links = obj.enabled_links()
        if links and links[0].supplier_product.is_slot:
            return links[0].supplier_product.slot_durations
        return []


class OfferSerializer(serializers.Serializer):
    """One user-selectable offer (attached bot product) — bot name is hidden."""
    offer_id = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    is_slot = serializers.SerializerMethodField()
    slot_durations = serializers.SerializerMethodField()

    def _audience(self):
        return self.context.get("audience", "retail")

    def get_offer_id(self, obj):
        return obj["link"].id

    def get_label(self, obj):
        return obj["link"].label(obj["index"])

    def get_price(self, obj):
        p = obj["link"].price_for(self._audience())
        return str(p) if p is not None else None

    def get_in_stock(self, obj):
        return obj["link"].supplier_product.in_stock

    def get_available(self, obj):
        return obj["link"].supplier_product.available

    def get_is_slot(self, obj):
        return obj["link"].supplier_product.is_slot

    def get_slot_durations(self, obj):
        return obj["link"].supplier_product.slot_durations
