from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Product = apps.get_model("product", "Product")
    used = set()
    for product in Product.objects.order_by("id"):
        base = slugify(product.title)[:250] or f"digital-tool-{product.id}"
        slug, number = base, 2
        while slug in used:
            slug = f"{base[:245]}-{number}"
            number += 1
        product.slug = slug
        product.save(update_fields=["slug"])
        used.add(slug)


class Migration(migrations.Migration):
    dependencies = [("product", "0003_product_notes")]
    operations = [
        # A previous interrupted schema edit can leave PostgreSQL's LIKE helper
        # index behind even though the migration transaction itself rolled back.
        # It is recreated automatically when the unique SlugField is applied.
        migrations.RunSQL(
            "DROP INDEX IF EXISTS product_product_slug_76cde0ae_like",
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Use an unindexed temporary column while existing rows are populated.
        # Adding a temporary SlugField here makes PostgreSQL queue the same LIKE
        # index that the final unique SlugField creates later in this migration.
        migrations.AddField(model_name="product", name="slug", field=models.CharField(blank=True, max_length=280, null=True)),
        migrations.AddField(model_name="product", name="seo_title", field=models.CharField(blank=True, default="", max_length=70)),
        migrations.AddField(model_name="product", name="meta_description", field=models.CharField(blank=True, default="", max_length=170)),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(model_name="product", name="slug", field=models.SlugField(blank=True, max_length=280, unique=True)),
    ]
