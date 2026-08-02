import django.db.models.deletion
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0002_binancedeposit"), ("product", "0004_product_slug_seo")]
    operations = [migrations.CreateModel(
        name="PromoCode",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("code", models.CharField(max_length=40, unique=True)),
            ("markup_percent", models.DecimalField(decimal_places=2, default=0, help_text="Percentage added on top of platform/base cost.", max_digits=7, validators=[django.core.validators.MinValueValidator(0)])),
            ("markup_flat_pkr", models.DecimalField(decimal_places=2, default=0, help_text="Flat PKR added after the percentage markup.", max_digits=12, validators=[django.core.validators.MinValueValidator(0)])),
            ("is_active", models.BooleanField(default=True)),
            ("starts_at", models.DateTimeField(blank=True, null=True)),
            ("expires_at", models.DateTimeField(blank=True, null=True)),
            ("max_uses", models.PositiveIntegerField(blank=True, null=True)),
            ("times_used", models.PositiveIntegerField(default=0, editable=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("product", models.ForeignKey(blank=True, help_text="Blank applies to every product.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="promo_codes", to="product.product")),
        ],
        options={"ordering": ["-created_at"]},
    )]
