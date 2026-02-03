from __future__ import annotations

import os
from collections import defaultdict
from typing import Optional

from django.core.cache import cache

_otel_meter = None
_otel_counters = {}
_LOCAL_COUNTERS = defaultdict(int)


def _init_otel():
    global _otel_meter
    if _otel_meter is not None:
        return _otel_meter
    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        provider = metrics.get_meter_provider()
        if provider is None or provider.__class__.__name__ == "_DefaultMeterProvider":
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
            insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
            exporter = OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
            reader = PeriodicExportingMetricReader(exporter)
            provider = MeterProvider(metric_readers=[reader])
            metrics.set_meter_provider(provider)
        _otel_meter = metrics.get_meter_provider().get_meter("tools", "1.0.0")
    except Exception:
        _otel_meter = None
    return _otel_meter


def _get_counter(name: str):
    meter = _init_otel()
    if not meter:
        return None
    counter = _otel_counters.get(name)
    if counter:
        return counter
    try:
        counter = meter.create_counter(name)
        _otel_counters[name] = counter
        return counter
    except Exception:
        return None


def _incr(key: str):
    counter = _get_counter(key)
    if counter:
        try:
            counter.add(1)
        except Exception:
            pass
    cache_key = f"telemetry:{key}"
    try:
        cache.add(cache_key, 0)
        cache.incr(cache_key)
    except Exception:
        _LOCAL_COUNTERS[cache_key] += 1


def inc_tool_enabled():
    _incr("tools_enabled")


def inc_tool_disabled():
    _incr("tools_disabled")


def inc_tool_list():
    _incr("tool_list_requests")


def inc_tool_schema():
    _incr("tool_schema_requests")


def inc_tool_validation(success: bool):
    _incr("tool_validations")
    if not success:
        _incr("tool_validation_failures")


def snapshot_counters():
    return dict(_LOCAL_COUNTERS)
