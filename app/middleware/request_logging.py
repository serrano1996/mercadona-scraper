"""ASGI middleware that logs the start/end of every HTTP request (spec
003-mercadona-scaper-logging, RF-6), tagged with a per-request id (RF-7)
so concurrent traffic can be correlated in the logs — including log lines
emitted by modules that know nothing about HTTP, via the ContextVar-based
filter in app/core/logging_config.py.

Runs as Starlette middleware (wraps every request before routing), so it
also covers requests that fail validation (422) before reaching a route
handler (spec.md caso limite).
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import bind_request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4().hex[:12]
        with bind_request_id(request_id):
            logger.info(
                "request start: %s %s params=%s",
                request.method,
                request.url.path,
                dict(request.query_params),
            )
            start = time.monotonic()
            response = await call_next(request)
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "request end: status=%s duration_ms=%.1f",
                response.status_code,
                duration_ms,
            )
        return response
