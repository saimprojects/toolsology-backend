from django.conf import settings
from django.http import HttpResponse
from django.utils.html import escape

from product.models import Product
from .models import BlogPost


def sitemap_xml(request):
    base = settings.FRONTEND_URL
    urls = [
        ("/", None, "daily", "1.0"),
        ("/products", None, "daily", "0.9"),
        ("/blog", None, "weekly", "0.8"),
        ("/about", None, "monthly", "0.6"),
        ("/contact", None, "monthly", "0.5"),
        ("/reviews", None, "weekly", "0.6"),
        ("/refund-policy", None, "yearly", "0.3"),
    ]
    for product in Product.objects.filter(status=True).only("slug", "updated_at"):
        urls.append((f"/product/{product.slug}", product.updated_at, "weekly", "0.8"))
    for post in BlogPost.objects.filter(is_published=True).only("slug", "updated_at"):
        urls.append((f"/blog/{post.slug}", post.updated_at, "monthly", "0.7"))

    rows = []
    for path, modified, frequency, priority in urls:
        lastmod = f"<lastmod>{modified.date().isoformat()}</lastmod>" if modified else ""
        rows.append(
            f"<url><loc>{escape(base + path)}</loc>{lastmod}"
            f"<changefreq>{frequency}</changefreq><priority>{priority}</priority></url>"
        )
    body = '<?xml version="1.0" encoding="UTF-8"?>' \
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(rows) + "</urlset>"
    return HttpResponse(body, content_type="application/xml")
