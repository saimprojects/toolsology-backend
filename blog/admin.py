from django.contrib import admin
from .models import BlogPost


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "focus_keyword", "is_published", "published_at", "updated_at")
    list_filter = ("is_published", "published_at")
    search_fields = ("title", "excerpt", "content", "focus_keyword")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        ("Article", {"fields": ("title", "slug", "excerpt", "featured_image", "content")}),
        ("SEO & AEO", {"fields": ("seo_title", "meta_description", "focus_keyword")}),
        ("Publishing", {"fields": ("author_name", "is_published", "published_at")}),
    )
