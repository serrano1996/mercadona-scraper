"""T4 — _parse_retry_after() parses the two HTTP-standard Retry-After
formats (seconds, HTTP-date), spec 002 RF-2/RF-3."""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

from app.scrapers.mercadona_client import _parse_retry_after


def test_parses_seconds() -> None:
    assert _parse_retry_after("7") == 7.0


def test_parses_http_date_in_the_future() -> None:
    future = datetime.now(UTC) + timedelta(seconds=10)

    result = _parse_retry_after(format_datetime(future, usegmt=True))

    assert result is not None
    assert 8 <= result <= 10


def test_http_date_in_the_past_clamps_to_zero() -> None:
    past = datetime.now(UTC) - timedelta(seconds=10)

    result = _parse_retry_after(format_datetime(past, usegmt=True))

    assert result == 0.0


def test_unparseable_value_returns_none() -> None:
    assert _parse_retry_after("not-a-number-or-a-date") is None


def test_missing_value_returns_none() -> None:
    assert _parse_retry_after(None) is None
