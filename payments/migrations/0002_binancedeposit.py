from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("reseller", "0001_initial"),
        ("sourcing", "0007_productsourcelink_short_description_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="BinanceDeposit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tx_id", models.CharField(db_index=True, max_length=160, unique=True)),
                ("coin", models.CharField(default="USDT", max_length=16)),
                ("network", models.CharField(blank=True, default="", max_length=32)),
                ("address", models.CharField(blank=True, default="", max_length=256)),
                ("amount", models.DecimalField(decimal_places=8, max_digits=24)),
                ("amount_pkr", models.DecimalField(decimal_places=2, max_digits=14)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                ("consumed_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="binance_payments", to="sourcing.order")),
                ("reseller", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="binance_deposits", to="reseller.reseller")),
            ],
            options={"ordering": ["-consumed_at"]},
        ),
    ]
