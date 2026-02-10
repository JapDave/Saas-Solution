from __future__ import annotations

from typing import Iterable
import time
from django.core.cache import cache


def _parse_rate(rate: str | None, default_limit: int, default_window_minutes: int) -> tuple[int, int]:
    if not rate:
        return default_limit, default_window_minutes
    try:
        num, unit = rate.split("/", 1)
        num = int(num)
        unit = unit.strip().lower()
        if unit in ("h", "hour", "hours"):
            return num, 60
        if unit in ("m", "min", "minute", "minutes"):
            return num, 1
        if unit in ("d", "day", "days"):
            return num, 60 * 24
    except Exception:
        return default_limit, default_window_minutes
    return default_limit, default_window_minutes


def _load_window(key: str, window_seconds: int) -> list[float]:
    hits = cache.get(key, [])
    now = time.time()
    filtered = [ts for ts in hits if ts > now - window_seconds]
    if len(filtered) != len(hits):
        cache.set(key, filtered, window_seconds)
    return filtered


def _store_hits(key: str, hits: list[float], window_seconds: int):
    cache.set(key, hits, window_seconds)


def check_rate_limit(
    keys: Iterable[str],
    *,
    rate: str | None = None,
    default_limit: int = 1,
    default_window_minutes: int = 1,
) -> tuple[bool, int]:
    """Return (blocked, retry_after_seconds)."""
    limit, window_minutes = _parse_rate(rate, default_limit, default_window_minutes)
    window_seconds = window_minutes * 60
    blocked = False
    retry_after = 0
    now = time.time()
    for key in keys:
        hits = _load_window(key, window_seconds)
        if len(hits) >= limit:
            blocked = True
            earliest = min(hits)
            retry_after = max(retry_after, int((earliest + window_seconds) - now))
    return blocked, max(retry_after, 0)


def record_rate_limit(
    keys: Iterable[str],
    *,
    rate: str | None = None,
    default_limit: int = 1,
    default_window_minutes: int = 1,
):
    limit, window_minutes = _parse_rate(rate, default_limit, default_window_minutes)
    window_seconds = window_minutes * 60
    now = time.time()
    for key in keys:
        hits = _load_window(key, window_seconds)
        hits.append(now)
        hits = [ts for ts in hits if ts > now - window_seconds][-limit * 2 :]
        _store_hits(key, hits, window_seconds)


def clear_rate_limit(keys: Iterable[str]):
    for key in keys:
        cache.delete(key)


class RateLimiter:
    """
    Common rate limiter wrapper for sliding-window limits.
    """

    def __init__(
        self,
        *,
        rate: str | None = None,
        default_limit: int = 1,
        default_window_minutes: int = 1,
    ):
        self.rate = rate
        self.default_limit = default_limit
        self.default_window_minutes = default_window_minutes

    def check(self, keys: Iterable[str]) -> tuple[bool, int]:
        return check_rate_limit(
            keys,
            rate=self.rate,
            default_limit=self.default_limit,
            default_window_minutes=self.default_window_minutes,
        )

    def record(self, keys: Iterable[str]) -> None:
        record_rate_limit(
            keys,
            rate=self.rate,
            default_limit=self.default_limit,
            default_window_minutes=self.default_window_minutes,
        )

    def clear(self, keys: Iterable[str]) -> None:
        clear_rate_limit(keys)
