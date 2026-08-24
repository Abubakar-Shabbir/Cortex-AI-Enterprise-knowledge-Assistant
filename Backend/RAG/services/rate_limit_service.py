"""
Rate Limiting

Pure django.core.cache.cache based - no new dependency, works against
the LocMemCache backend already implicit everywhere else in this
project (see CLAUDE.md's Caching section). Covers login attempts, OTP
resend/verify, password-reset requests, and signup - every place in
this feature set that needs an abuse guard.

Fails OPEN on a cache backend error (never raises) - this guards abuse,
not correctness, so a cache hiccup should never itself lock a user out
or 500 a request.

Note: LocMemCache is per-process. On a multi-process deployment these
limits are per-worker-process, not global - the same caveat every other
LocMemCache-backed cache in this project already carries (see
CLAUDE.md's Caching section on context_processors/BM25/graph caches).
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window counter keyed on `key`. False for the first `limit`
    calls within `window_seconds` of the first call; True after that,
    until the window naturally expires from cache.
    """

    cache_key = f"ratelimit:{key}"

    try:
        count = cache.get(cache_key)

        if count is None:
            cache.set(cache_key, 1, timeout=window_seconds)
            return False

        if count >= limit:
            return True

        cache.incr(cache_key)
        return False

    except Exception:
        logger.exception("rate_limit_service.is_rate_limited: cache error for key=%s, failing open", key)
        return False


def get_cooldown_remaining_seconds(key: str) -> int:
    """0 if no active cooldown for `key`. LocMemCache doesn't expose a TTL-remaining read, so this stores the cooldown's own expiry timestamp rather than relying on the cache backend to report it."""

    import time

    expires_at = cache.get(f"cooldown:{key}")

    if not expires_at:
        return 0

    remaining = int(expires_at - time.time())
    return max(0, remaining)


def start_cooldown(key: str, seconds: int) -> None:
    import time

    try:
        cache.set(f"cooldown:{key}", time.time() + seconds, timeout=seconds)
    except Exception:
        logger.exception("rate_limit_service.start_cooldown: cache error for key=%s", key)
