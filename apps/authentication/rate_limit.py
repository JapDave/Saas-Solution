from __future__ import annotations

import time
from typing import Iterable, Tuple

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def _load_window(key: str, window_seconds: int) -> list[float]:
    hits = cache.get(key, [])
    now = time.time()
    filtered = [ts for ts in hits if ts > now - window_seconds]
    if len(filtered) != len(hits):
        cache.set(key, filtered, window_seconds)
    return filtered


def _store_hits(key: str, hits: list[float], window_seconds: int):
    cache.set(key, hits, window_seconds)


def check_login_rate_limit(
    *,
    email: str | None,
    ip: str | None,
    limit: int | None = None,
    window_minutes: int | None = None,
) -> Tuple[bool, int]:
    """Return (blocked, retry_after_seconds)."""
    limit = limit or getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3) or 3
    window_minutes = window_minutes or getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES", 10) or 10
    window_seconds = window_minutes * 60
    keys = []
    if ip:
        keys.append(f"auth:login:ip:{ip}")
    if email:
        keys.append(f"auth:login:email:{email.lower()}")

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


def record_login_failure(
    *,
    email: str | None,
    ip: str | None,
    limit: int | None = None,
    window_minutes: int | None = None,
):
    limit = limit or getattr(settings, "AUTH_LOGIN_RATE_LIMIT_ATTEMPTS", 3) or 3
    window_minutes = window_minutes or getattr(settings, "AUTH_LOGIN_RATE_LIMIT_WINDOW_MINUTES", 10) or 10
    window_seconds = window_minutes * 60
    now = time.time()
    keys: list[str] = []
    if ip:
        keys.append(f"auth:login:ip:{ip}")
    if email:
        keys.append(f"auth:login:email:{email.lower()}")
    for key in keys:
        hits = _load_window(key, window_seconds)
        hits.append(now)
        hits = [ts for ts in hits if ts > now - window_seconds][-limit * 2 :]
        _store_hits(key, hits, window_seconds)


def clear_login_failures(*, email: str | None, ip: str | None):
    keys: list[str] = []
    if ip:
        keys.append(f"auth:login:ip:{ip}")
    if email:
        keys.append(f"auth:login:email:{email.lower()}")
    for key in keys:
        cache.delete(key)
