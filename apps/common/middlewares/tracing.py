"""
Lightweight OTEL tracing middleware to emit a span per HTTP request.
Designed as a fallback when auto-instrumentation is unavailable.
"""
from time import perf_counter
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


tracer = trace.get_tracer("hudhud.web")


class TracingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = perf_counter()
        span = tracer.start_span(
            name=f"{request.method} {request.path}",
            attributes={
                "http.method": request.method,
                "http.target": request.get_full_path(),
                "http.host": request.get_host(),
            },
        )
        try:
            response = self.get_response(request)
            span.set_attribute("http.status_code", getattr(response, "status_code", 0))
            return response
        except Exception as exc:  # pragma: no cover - pass through
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            elapsed_ms = (perf_counter() - start) * 1000
            span.set_attribute("http.duration_ms", round(elapsed_ms, 2))
            if getattr(request, "resolver_match", None):
                span.set_attribute("http.route", request.resolver_match.route or request.path)
            user = getattr(request, "user", None)
            if user and getattr(user, "is_authenticated", False):
                span.set_attribute("enduser.id", str(user.pk))
                if getattr(user, "email", None):
                    span.set_attribute("enduser.email", user.email)
            span.end()
