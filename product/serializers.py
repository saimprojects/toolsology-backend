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
    

    class Meta:
        model = Product
        fields = [
            'id',
            'title',
            'description',
            'price',
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


class WhatsAppSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppSettings
        fields = ['whatsapp_number']
