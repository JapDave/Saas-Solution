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


# Parse rate strings like "10/hour" -> (10, 60)
def _parse_rate(rate: str | None, default_limit: int, default_window_minutes: int):
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


# Generic refresh rate limit (ip/user based)
def _refresh_keys(ip: str | None, user_id: int | None):
    keys = []
    if ip:
        keys.append(f"auth:refresh:ip:{ip}")
    if user_id:
        keys.append(f"auth:refresh:user:{user_id}")
    return keys


def check_refresh_rate_limit(*, ip: str | None, user_id: int | None = None, limit: int | None = None, window_minutes: int | None = None):
    default_limit, default_window_minutes = _parse_rate(
        getattr(settings, "AUTH_RATE_LIMIT_REFRESH", None), 10, 60
    )
    limit = limit or default_limit
    window_minutes = window_minutes or default_window_minutes
    window_seconds = window_minutes * 60
    keys = _refresh_keys(ip, user_id)
    if not keys:
        return False, 0
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


def record_refresh_attempt(*, ip: str | None, user_id: int | None = None, limit: int | None = None, window_minutes: int | None = None):
    default_limit, default_window_minutes = _parse_rate(
        getattr(settings, "AUTH_RATE_LIMIT_REFRESH", None), 10, 60
    )
    limit = limit or default_limit
    window_minutes = window_minutes or default_window_minutes
    window_seconds = window_minutes * 60
    keys = _refresh_keys(ip, user_id)
    if not keys:
        return
    now = time.time()
    for key in keys:
        hits = _load_window(key, window_seconds)
        hits.append(now)
        hits = [ts for ts in hits if ts > now - window_seconds][-limit * 2 :]
        _store_hits(key, hits, window_seconds)


# Password reset rate limit: 3 per email and 3 per IP
def check_password_reset_rate_limit(*, email: str | None, ip: str | None, limit: int = 3, window_minutes: int = 60):
    window_seconds = window_minutes * 60
    now = time.time()
    blocked = False
    retry_after = 0
    keys = []
    if ip:
        keys.append(f"auth:pwreset:ip:{ip}")
    if email:
        keys.append(f"auth:pwreset:email:{email.lower()}")
    for key in keys:
        hits = _load_window(key, window_seconds)
        if len(hits) >= limit:
            blocked = True
            earliest = min(hits)
            retry_after = max(retry_after, int((earliest + window_seconds) - now))
    return blocked, retry_after


def record_password_reset_attempt(*, email: str | None, ip: str | None, limit: int = 3, window_minutes: int = 60):
    window_seconds = window_minutes * 60
    now = time.time()
    keys = []
    if ip:
        keys.append(f"auth:pwreset:ip:{ip}")
    if email:
        keys.append(f"auth:pwreset:email:{email.lower()}")
    for key in keys:
        hits = _load_window(key, window_seconds)
        hits.append(now)
        hits = [ts for ts in hits if ts > now - window_seconds][-limit * 2 :]
        _store_hits(key, hits, window_seconds)
