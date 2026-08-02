from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sourcing", "0008_order_promo_code"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supplierbot",
            name="bot_source",
            field=models.CharField(
                choices=[
                    ("primary", "Telegram (primary)"),
                    ("telegram2", "Telegram (2nd)"),
                    ("binance", "Binance bot"),
                    ("bybit", "Bybit bot"),
                    ("sson", "SSON Digital Works"),
                    ("other", "Other"),
                ],
                default="other",
                help_text="Informational only; the key itself decides the real flow.",
                max_length=20,
            ),
        ),
    ]
