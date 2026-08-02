from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reseller", "0001_initial")]
    operations = [migrations.CreateModel(
        name="ResellerApiKey",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(default="Primary", max_length=80)),
            ("prefix", models.CharField(db_index=True, max_length=12)),
            ("key_hash", models.CharField(max_length=64, unique=True)),
            ("is_active", models.BooleanField(default=True)),
            ("last_used_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("reseller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to="reseller.reseller")),
        ], options={"ordering": ["-created_at"]},
    )]
