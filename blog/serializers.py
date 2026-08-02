from rest_framework import serializers
from .models import BlogPost


class BlogPostSerializer(serializers.ModelSerializer):
    featured_image = serializers.SerializerMethodField()

    class Meta:
        model = BlogPost
        fields = ["id", "title", "slug", "excerpt", "content", "featured_image",
                  "author_name", "seo_title", "meta_description", "focus_keyword",
                  "published_at", "updated_at"]

    def get_featured_image(self, obj):
        return obj.featured_image.url if obj.featured_image else None
