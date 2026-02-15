from __future__ import annotations

from collections import defaultdict

from django.core.cache import cache

_LOCAL_COUNTERS = defaultdict(int)


def _incr(key: str):
    cache_key = f"telemetry:{key}"
    try:
        cache.add(cache_key, 0)
        cache.incr(cache_key)
    except Exception:
        _LOCAL_COUNTERS[cache_key] += 1


def inc_agents_created():
    _incr("agents_created")


def inc_agents_deleted():
    _incr("agents_deleted")


def inc_agents_cloned():
    _incr("agents_cloned")


def inc_agent_versions_saved():
    _incr("agent_versions_saved")


def inc_agent_versions_switched():
    _incr("agent_versions_switched")


def inc_agent_updates():
    _incr("agent_updates")


def inc_subscription_check_failures():
    _incr("agent_subscription_check_failures")


def snapshot_counters():
    return dict(_LOCAL_COUNTERS)
