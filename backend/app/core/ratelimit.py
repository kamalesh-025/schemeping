"""A small in-process rate limiter for the public endpoints.

Purpose: blunt abuse of the OTP request, chat and event endpoints. It is
deliberately simple - a fixed window per key in memory - because the
platform runs one API container. Behind several instances, move it to
Redis; the interface (``allow``) stays the same.

The citizen-facing limits that must be exact (per user, per hour) live in
the services (``chat.check_rate_limit``, ``notifications`` rate limit);
this one protects the network edge.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.logging import get_logger

logger = get_logger(__name__)

_MAX_KEYS = 10_000


class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            hits = [stamp for stamp in self._hits[key] if stamp > cutoff]
            if len(hits) >= limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > _MAX_KEYS:
                # Drop keys nobody has touched recently.
                for stale in [
                    candidate
                    for candidate, stamps in self._hits.items()
                    if not stamps or stamps[-1] < cutoff
                ]:
                    self._hits.pop(stale, None)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = _FixedWindowLimiter()


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def enforce(
    request: Request, *, limit: int, window_seconds: int, scope: str
) -> None:
    """Raise 429 when the caller exceeds the budget for ``scope``."""
    key = f"{scope}:{client_key(request)}"
    if not _limiter.allow(key, limit, window_seconds):
        logger.warning("rate_limit_exceeded", extra={"scope": scope})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait a moment and try again.",
        )


def allow_key(key: str, *, limit: int, window_seconds: int) -> bool:
    """Count one hit for an arbitrary key (e.g. a single mobile number)."""
    return _limiter.allow(key, limit, window_seconds)
