
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles import views as staticfiles_views
from django.http import JsonResponse
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from blog.sitemap import sitemap_xml


def health_check(request):
    """Lightweight Railway health check with no database dependency."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # Some Railway service-level configurations override railway.toml and
    # probe the application root. Keep both endpoints healthy.
    path("", health_check, name="root-health-check"),
    path("health/", health_check, name="health-check"),
    # Railway can override the repository start command and skip collectstatic.
    # Keep a production fallback so admin/Jazzmin assets still resolve through
    # Django's static-file finders instead of leaving the admin unstyled.
    path(
        "static/<path:path>",
        staticfiles_views.serve,
        {"insecure": True},
        name="static-fallback",
    ),
    path('sitemap.xml', sitemap_xml, name='sitemap'),
    path('admin/', admin.site.urls),
    # API endpoints from product app
    path('api/', include('product.urls')),
    # Sourcing storefront + reseller panel
    path('api/sourcing/', include('sourcing.urls')),
    # Payments (methods, SMS webhook, checkout)
    path('api/payments/', include('payments.urls')),
    # Reseller panel (signup, wallet, purchase)
    path('api/reseller/', include('reseller.urls')),
    # Customer accounts (signup, orders)
    path('api/customer/', include('customer.urls')),
    path('api/blog/', include('blog.urls')),
    # JWT authentication endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("ckeditor/", include("ckeditor_uploader.urls")),

]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
