import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev"))

# Configure OTEL tracer provider eagerly so WSGI middleware can emit spans even if auto-instrumentation fails
try:  # pragma: no cover - optional instrumentation
    from opentelemetry import trace  # type: ignore
    from opentelemetry.sdk.resources import Resource  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # type: ignore

    _svc_name = os.getenv("OTEL_SERVICE_NAME", "platform")
    _svc_ns = os.getenv("APM_SERVICE_NAMESPACE", "hudhud")
    _env = os.getenv("APM_ENVIRONMENT", "local")
    _endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    _insecure = str(os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true")).lower() in {"1", "true", "yes", "on"}

    resource = Resource.create(
        {
            "service.name": _svc_name,
            "service.namespace": _svc_ns,
            "deployment.environment": _env,
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=_endpoint, insecure=_insecure)))
    trace.set_tracer_provider(provider)
except Exception:
    provider = None

application = get_wsgi_application()

# Wrap WSGI app with OTEL middleware to emit HTTP spans
try:  # pragma: no cover - optional instrumentation
    from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware  # type: ignore

    application = OpenTelemetryMiddleware(application)
except Exception:
    pass
