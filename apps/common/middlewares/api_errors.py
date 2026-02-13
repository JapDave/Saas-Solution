from __future__ import annotations

from django.http import JsonResponse

from apps.common.exceptions import INSUFFICIENT_PERMISSIONS


class ApiErrorResponseMiddleware:
    """Ensure API responses are JSON, even for HTML 4xx/5xx fallbacks."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response is None:
            return response

        if not getattr(request, "path", "").startswith("/api/"):
            return response

        status = getattr(response, "status_code", 200)
        if status < 400:
            return response

        content_type = (response.get("content-type") or "").lower()
        if "application/json" in content_type:
            return response

        if status == 400:
            payload = {"code": "INVALID_DATA", "message": "Bad request."}
        elif status == 401:
            payload = {"code": "UNAUTHORIZED", "message": "Authentication required."}
        elif status == 403:
            payload = {"code": INSUFFICIENT_PERMISSIONS, "message": "Permission denied."}
        elif status == 404:
            payload = {"code": "NOT_FOUND", "message": "Not found."}
        else:
            payload = {"code": "ERROR", "message": "Internal server error."}

        return JsonResponse(payload, status=status)
