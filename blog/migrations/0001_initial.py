import cloudinary.models
import ckeditor.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(
        name="BlogPost",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("title", models.CharField(max_length=255)),
            ("slug", models.SlugField(blank=True, max_length=280, unique=True)),
            ("excerpt", models.TextField(max_length=500)),
            ("content", ckeditor.fields.RichTextField()),
            ("featured_image", cloudinary.models.CloudinaryField(blank=True, max_length=255, null=True, verbose_name="featured image")),
            ("author_name", models.CharField(default="Toolsology Editorial", max_length=100)),
            ("seo_title", models.CharField(blank=True, default="", max_length=70)),
            ("meta_description", models.CharField(blank=True, default="", max_length=170)),
            ("focus_keyword", models.CharField(blank=True, default="", max_length=120)),
            ("is_published", models.BooleanField(default=False)),
            ("published_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ],
        options={"ordering": ["-published_at", "-created_at"]},
    )]
