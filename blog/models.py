from django.db import models
from django.template.defaultfilters import slugify
from ckeditor.fields import RichTextField
from cloudinary.models import CloudinaryField


class BlogPost(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    excerpt = models.TextField(max_length=500)
    content = RichTextField()
    featured_image = CloudinaryField("featured image", blank=True, null=True)
    author_name = models.CharField(max_length=100, default="Toolsology Editorial")
    seo_title = models.CharField(max_length=70, blank=True, default="")
    meta_description = models.CharField(max_length=170, blank=True, default="")
    focus_keyword = models.CharField(max_length=120, blank=True, default="")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:250] or "digital-tools-guide"
            candidate, number = base, 2
            while BlogPost.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:245]}-{number}"
                number += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
