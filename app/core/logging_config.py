"""Central logging configuration (spec 003-mercadona-scaper-logging, RF-1)
and the request-id correlation mechanism (RF-7): the middleware
(app/middleware/request_logging.py) binds a request-id via
`bind_request_id` for the lifetime of each HTTP request, and
`_RequestIdFilter` tags every LogRecord that reaches our handler with it
— including records from modules that know nothing about HTTP
(mercadona_client.py, cache.py).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        return True


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


def configure_logging(level: str) -> None:
    """Sets the root logger's level and, the first time it's called, adds
    our own formatted handler with the request-id filter. Deliberately
    doesn't use logging.basicConfig(force=True): that would wipe out any
    handler already on the root logger (e.g. pytest's caplog), breaking
    log capture in tests that call this more than once (see Decision D5
    in plan.md — this runs once per lifespan entry, and integration tests
    re-enter the lifespan per test)."""
    root = logging.getLogger()
    root.setLevel(level)
    if not any(getattr(h, "_is_app_handler", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._is_app_handler = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        handler.addFilter(_RequestIdFilter())
        root.addHandler(handler)
