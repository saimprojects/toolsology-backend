from django.apps import AppConfig


class SourcingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sourcing"
    verbose_name = "Sourcing / Supplier Bots"

    def ready(self):
        _patch_jazzmin_format_html()


def _patch_jazzmin_format_html():
    """Fix django-jazzmin pagination crash on Django 6.0.

    Django 6.0 removed support for calling format_html() with no args/kwargs,
    but jazzmin's `jazzmin_paginator_number` tag does exactly that, which breaks
    any admin changelist that paginates (>1 page). See jazzmin issue #517.

    We restore the pre-6.0 behaviour ONLY inside jazzmin's module namespace, so
    the rest of Django keeps the new, stricter behaviour.
    """
    try:
        from jazzmin.templatetags import jazzmin as jz
        from django.utils.html import format_html as _dj_format_html
        from django.utils.safestring import mark_safe
    except Exception:
        return

    if getattr(jz, "_format_html_patched", False):
        return

    def _lenient_format_html(format_string, *args, **kwargs):
        if not args and not kwargs:
            return mark_safe(format_string)
        return _dj_format_html(format_string, *args, **kwargs)

    jz.format_html = _lenient_format_html
    jz._format_html_patched = True
