from __future__ import annotations

from django.db import models
from django.template.defaultfilters import slugify  # type: ignore
from ckeditor.fields import RichTextField  # type: ignore
from cloudinary.models import CloudinaryField
import re
from django.core.exceptions import ValidationError


class Category(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    status = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    title = models.CharField(max_length=255)
    description = RichTextField()
    notes = RichTextField(blank=True, default="")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    categories = models.ManyToManyField(Category, related_name='products')
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.title

    def main_image(self) -> str | None:
        main = self.images.filter(is_main=True).first() or self.images.first()
        return main.image.url if main else None


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        related_name='images',
        on_delete=models.CASCADE
    )
    image = CloudinaryField('image')
    is_main = models.BooleanField(default=False)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordering']

    def save(self, *args, **kwargs):
        # ensure only one main image per product
        if self.is_main:
            ProductImage.objects.filter(
                product=self.product,
                is_main=True
            ).exclude(pk=self.pk).update(is_main=False)

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Image for {self.product.title}"


class ProductPlan(models.Model):
    product = models.ForeignKey(
        Product,
        related_name='plans',
        on_delete=models.CASCADE
    )
    title = models.CharField(max_length=100)
    duration_months = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['duration_months']
        unique_together = ('product', 'duration_months')

    def __str__(self):
        return f"{self.product.title} - {self.title}"


class Review(models.Model):
    product = models.ForeignKey(Product, related_name='reviews', on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=255)
    rating = models.PositiveIntegerField(default=5)
    comment = models.TextField(blank=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.customer_name} on {self.product.title}"


def validate_pk_whatsapp(value: str):
    if not re.fullmatch(r"^\+92\d{10}$", value):
        raise ValidationError(
            "WhatsApp number must be in format: +92XXXXXXXXXX"
        )


class WhatsAppSettings(models.Model):
    whatsapp_number = models.CharField(
        max_length=13,
        validators=[validate_pk_whatsapp],
        help_text="Format: +92XXXXXXXXXX"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.whatsapp_number
