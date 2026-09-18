"""T2 — configure_logging() sets the root logger's level and installs a
handler whose filter tags every record with the current request's id (or
"-" outside any request context), so RF-7's correlation works for logs
emitted by modules that know nothing about HTTP (mercadona_client.py,
cache.py)."""

import logging

from app.core.logging_config import _RequestIdFilter, bind_request_id, configure_logging


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )


def test_configure_logging_sets_root_level() -> None:
    configure_logging("DEBUG")

    assert logging.getLogger().level == logging.DEBUG

    configure_logging("WARNING")

    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_is_idempotent_about_handlers() -> None:
    configure_logging("INFO")
    handlers_after_first = list(logging.getLogger().handlers)

    configure_logging("INFO")

    assert logging.getLogger().handlers == handlers_after_first


def test_filter_defaults_request_id_to_dash_outside_request_context() -> None:
    record = _make_record()

    _RequestIdFilter().filter(record)

    assert record.request_id == "-"


def test_filter_uses_bound_request_id_inside_context() -> None:
    record = _make_record()

    with bind_request_id("abc123"):
        _RequestIdFilter().filter(record)

    assert record.request_id == "abc123"


def test_request_id_resets_after_context_exits() -> None:
    with bind_request_id("abc123"):
        pass

    record = _make_record()
    _RequestIdFilter().filter(record)

    assert record.request_id == "-"
