"""Security headers and request-ID correlation (Phase 6 Part D).

Every response carries a small set of hardening headers, and every request
gets an id (``X-Request-ID``) that is logged and echoed back so a support
request can be traced through the logs without exposing any personal data.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

RequestHandler = Callable[[Request], Awaitable[Response]]

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(self), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Permitted-Cross-Domain-Policies": "none",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add hardening headers, a request id and a duration log line."""

    async def dispatch(
        self, request: Request, call_next: RequestHandler
    ) -> Response:
        settings = get_settings()
        request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers["X-Request-ID"] = request_id
        if settings.is_production:
            # HSTS only over HTTPS in production.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
