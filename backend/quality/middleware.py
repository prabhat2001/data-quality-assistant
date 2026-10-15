"""Allow the Next.js app to call the API directly during local development."""

from django.http import HttpResponse

ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        if request.method == "OPTIONS" and origin in ALLOWED_ORIGINS:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if origin in ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
