from __future__ import annotations

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class CSPMiddleware(MiddlewareMixin):
    """Apply a default Content-Security-Policy header based on baseline settings."""

    def process_response(self, request, response):
        if response.has_header("Content-Security-Policy"):
            return response

        directives = []
        def _add(name):
            values = getattr(settings, name, [])
            if values:
                directives.append(f"{name.replace('_', '-')} {' '.join(values)}")

        _add("CSP_DEFAULT_SRC")
        _add("CSP_CONNECT_SRC")
        _add("CSP_SCRIPT_SRC")
        _add("CSP_STYLE_SRC")
        _add("CSP_IMG_SRC")
        _add("CSP_FONT_SRC")

        if directives:
            response["Content-Security-Policy"] = "; ".join(directives)
        return response
