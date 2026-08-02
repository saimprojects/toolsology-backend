from django.utils import timezone
from rest_framework import authentication, exceptions
from .models import ResellerApiKey


class ResellerApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        raw = request.headers.get("X-API-Key", "")
        if not raw:
            return None
        key = ResellerApiKey.authenticate(raw)
        if not key:
            raise exceptions.AuthenticationFailed("Invalid or inactive API key.")
        key.last_used_at = timezone.now()
        key.save(update_fields=["last_used_at"])
        request.reseller = key.reseller
        return key.reseller.user, key
