from django.http import JsonResponse


class RailwayHealthCheckMiddleware:
    """Answer Railway's private health probe before Django validates Host."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/":
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
