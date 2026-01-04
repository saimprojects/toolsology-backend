from django.contrib import admin
from django.db.models import Count
from .models import (
    Product,
    ProductImage,
    Category,
    Review,
    WhatsAppSettings,
    ProductPlan,
)


# =========================
# Inline Admins
# =========================

class ProductPlanInline(admin.TabularInline):
    model = ProductPlan
    extra = 1
    fields = ("title", "duration_months", "price", "is_active")
    ordering = ("duration_months",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "is_main", "ordering")
    ordering = ("ordering",)


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    readonly_fields = ("created_at",)
    fields = ("customer_name", "rating", "comment", "status", "created_at")


# =========================
# Product Admin
# =========================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "plans_count",
        "images_count",
        "status",
        "created_at",
    )
    list_filter = ("status", "categories")
    search_fields = ("title",)
    filter_horizontal = ("categories",)
    inlines = [
        ProductPlanInline,
        ProductImageInline,
        ReviewInline,
    ]
    ordering = ("-created_at",)

    # ✅ Minimal change: notes show in admin form
    fieldsets = (
        (None, {"fields": ("title", "description", "notes", "price", "categories", "status")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _plans_count=Count("plans"),
            _images_count=Count("images"),
        )

    @admin.display(description="Plans")
    def plans_count(self, obj):
        return obj._plans_count

    @admin.display(description="Images")
    def images_count(self, obj):
        return obj._images_count


# =========================
# Product Plan Admin
# =========================

@admin.register(ProductPlan)
class ProductPlanAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "title",
        "duration_display",
        "price",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("product__title", "title")
    ordering = ("product", "duration_months")

    @admin.display(description="Duration")
    def duration_display(self, obj):
        if obj.duration_months == 0:
            return "Lifetime"
        return f"{obj.duration_months} Month(s)"


# =========================
# Category Admin
# =========================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "status")
    list_filter = ("status",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


# =========================
# Review Admin
# =========================

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "customer_name",
        "rating",
        "status",
        "created_at",
    )
    list_filter = ("status", "rating")
    search_fields = ("customer_name", "product__title")
    readonly_fields = ("created_at",)


# =========================
# WhatsApp Settings (Singleton)
# =========================

@admin.register(WhatsAppSettings)
class WhatsAppSettingsAdmin(admin.ModelAdmin):
    list_display = ("whatsapp_number", "updated_at")

    def has_add_permission(self, request):
        try:
            return not WhatsAppSettings.objects.exists()
        except Exception:
            # table doesn't exist yet
            return True

    def has_delete_permission(self, request, obj=None):
        return False
