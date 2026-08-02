"""
Serializers to convert model instances into JSON for API responses and
to validate incoming data for creation and updates.
"""
from rest_framework import serializers
from .models import (
    Category,
    Product,
    ProductImage,
    Review,
    WhatsAppSettings,
    ProductPlan,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class ProductImageSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_main', 'ordering']

    def get_image(self, obj):
        # return full Cloudinary URL
        if obj.image:
            return obj.image.url
        return None


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = [
            'id',
            'customer_name',
            'rating',
            'comment',
            'created_at',
            
        ]


class ProductPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPlan
        fields = [
            'id',
            'title',
            'duration_months',
            'price',
        ]


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    plans = ProductPlanSerializer(many=True, read_only=True)
    main_image = serializers.SerializerMethodField()
    # Live retail price from the offers system (same as checkout). This is what
    # the cards should show, not the legacy `price` column.
    store_price = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'slug',
            'title',
            'seo_title',
            'meta_description',
            'description',
            'price',
            'store_price',
            'in_stock',
            'status',
            'categories',
            'images',
            'main_image',
            'reviews',
            'plans',
            'created_at',
            'updated_at',
        ]

    def get_main_image(self, obj):
        img = obj.images.filter(is_main=True).first() or obj.images.first()
        return img.image.url if img else None

    def _summary(self, obj):
        # Cache per-instance so store_price + in_stock don't recompute.
        if not hasattr(obj, "_offer_summary_cache"):
            from sourcing.pricing import offer_summary
            obj._offer_summary_cache = offer_summary(obj, "retail")
        return obj._offer_summary_cache

    def get_store_price(self, obj):
        price, _ = self._summary(obj)
        return str(price) if price is not None else None

    def get_in_stock(self, obj):
        _, in_stock = self._summary(obj)
        return in_stock


class WhatsAppSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppSettings
        fields = ['whatsapp_number']
