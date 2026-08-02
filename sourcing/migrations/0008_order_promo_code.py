from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sourcing", "0007_productsourcelink_short_description_and_more"), ("payments", "0003_promocode")]
    operations = [migrations.AddField(
        model_name="order", name="promo_code",
        field=models.CharField(blank=True, default="", max_length=40),
    )]
