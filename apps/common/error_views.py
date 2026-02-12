from __future__ import annotations

from django.http import JsonResponse

from apps.common.exceptions import INSUFFICIENT_PERMISSIONS


def json_bad_request(request, exception=None):
    return JsonResponse(
        {"code": "INVALID_DATA", "message": "Bad request."},
        status=400,
    )


def json_permission_denied(request, exception=None):
    return JsonResponse(
        {"code": INSUFFICIENT_PERMISSIONS, "message": "Permission denied."},
        status=403,
    )


def json_not_found(request, exception=None):
    return JsonResponse(
        {"code": "NOT_FOUND", "message": "Not found."},
        status=404,
    )


def json_server_error(request):
    return JsonResponse(
        {"code": "ERROR", "message": "Internal server error."},
        status=500,
    )
