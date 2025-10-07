from __future__ import annotations

from typing import Optional, Tuple, Dict
from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


def _limits() -> Dict[str, str]:
    # Your single source of truth
    return getattr(settings, "DYNAMIC_RATELIMITS", {}) or {}


def _infer_key(path: str, method: str) -> Optional[str]:
    """
    Infer a rate key from path + method when the view does not provide one.
    Matches your provided keys in DYNAMIC_RATELIMITS.
    """
    p = (path or "").lower()
    m = (method or "GET").upper()

    if "/organizations" in p:
        if m == "GET":
            return "org.read.user"
        if m in ("PUT", "PATCH"):
            return "org.update.user"
        if m == "POST":
            return "org.create.owner"
        if m == "DELETE":
            return "org.delete.owner"
        return None

    if "/teams" in p:
        if "/members" in p:
            if m in ("POST", "DELETE"):
                return "team.manage_members.org"
            return None
        if m == "GET":
            return "team.read.user"
        if m in ("PUT", "PATCH"):
            return "team.update.org"
        if m == "POST":
            return "team.create.org"
        if m == "DELETE":
            return "team.delete.org"
        return None

    if "/accounts" in p:
        if m == "GET":
            return "acc.read.user"
        if m in ("PUT", "PATCH"):
            return "acc.update.user"
        if m == "POST":
            return "acc.create.admin"
        if m == "DELETE":
            return "acc.delete.admin"
        return None

    return None


class DynamicScopedRateThrottle(SimpleRateThrottle):
    """
    DRF throttle that:
      - Reads limits from settings.DYNAMIC_RATELIMITS (not DEFAULT_THROTTLE_RATES)
      - Uses per-view/viewset `throttle_scope` if provided
      - Else infers a key from URL + HTTP method (accounts/orgs out of the box)
      - If no key or no rate is found, throttling is disabled (no crash)
    """

    scope = "dynamic"  # ignored for rate lookup; we override get_rate()

    # We compute the key *before* DRF parses the rate; DRF calls get_cache_key()
    # first, then get_rate(). We stash both the chosen key and the rate.
    def get_cache_key(self, request, view):
        key, rate = self._resolve_scope_and_rate(request, view)

        # Keep chosen scope for cache segmentation, but do *not* require it in DEFAULT_THROTTLE_RATES
        self._chosen_scope = key or "dynamic"
        self._chosen_rate = rate  # may be None -> throttling disabled

        ident = self.get_ident(request)
        if ident is None:
            return None

        # Use chosen scope in the cache key to isolate buckets per action
        return self.cache_format % {"scope": self._chosen_scope, "ident": ident}

    def get_rate(self) -> Optional[str]:
        # DRF will disable throttling if this returns None
        return getattr(self, "_chosen_rate", None)

    # ------------- helpers -------------

    def _resolve_scope_and_rate(self, request, view) -> Tuple[Optional[str], Optional[str]]:
        limits = _limits()

        # 1) Explicit scope from the view (preferred)
        key = getattr(view, "throttle_scope", None)
        if not key and hasattr(view, "get_throttle_scope"):
            try:
                key = view.get_throttle_scope(request)  # optional custom hook
            except Exception:
                key = None

        # 2) Infer from path + method
        if not key:
            key = _infer_key(request.path, request.method)

        # 3) Lookup rate in DYNAMIC_RATELIMITS
        if key:
            rate = limits.get(key)
            return key, rate

        # 4) No key → no throttling
        return None, None
