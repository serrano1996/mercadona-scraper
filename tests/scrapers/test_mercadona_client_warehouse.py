"""T2/T3/T4 — 007-mercadona-scraper-warehouse-resolution: WarehouseHeaderMissing
is a plain domain exception, sibling of AlgoliaCredentialsUnavailable
(Decision D4 in plan.md). T3 covers MercadonaClient.resolve_warehouse's
happy path against Mercadona's real change-pc endpoint (verified live
2026-09-24, see spec.md). T4 adds its error cases, including the
regression that a 404 (RF-9) and any other non-429 4xx (RF-13) are NOT
retried — Decision D5 in plan.md: `_error_for_response` already returns
None for those on the first attempt, so this file only pins the contract
with tests, it doesn't change `_request_with_retry`."""

import logging
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.core.config import Settings
from app.scrapers.mercadona_client import (
    AlgoliaCredentialsUnavailable,
    MercadonaClient,
    WarehouseHeaderMissing,
)

CHANGE_PC_URL = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"


def test_warehouse_header_missing_is_instantiable() -> None:
    error = WarehouseHeaderMissing()

    assert isinstance(error, Exception)


def test_warehouse_header_missing_accepts_optional_message() -> None:
    error = WarehouseHeaderMissing("Mercadona returned 200 without x-customer-wh")

    assert str(error) == "Mercadona returned 200 without x-customer-wh"


def test_warehouse_header_missing_is_not_algolia_credentials_unavailable() -> None:
    assert not issubclass(WarehouseHeaderMissing, AlgoliaCredentialsUnavailable)


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        RETRY_MAX_ATTEMPTS=3,
        RETRY_BASE_DELAY=0.0,
        RETRY_JITTER_MAX_S=0.0,
    )


async def test_resolve_warehouse_returns_header_value_on_success() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(
            return_value=httpx.Response(
                200, headers={"x-customer-wh": "mad3", "x-customer-pc": "28001"}
            )
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("28001")

    assert warehouse == "mad3"
    assert route.calls.last.request.method == "PUT"
    assert route.calls.last.request.content == b'{"new_postal_code":"28001"}'


async def test_resolve_warehouse_returns_opaque_ids_unchanged() -> None:
    """Ids like `4701` (Canarias) or `3842` (Baleares) are opaque Mercadona
    identifiers, not necessarily 4-letter codes — no format is assumed
    (spec.md, Caso límite)."""
    with respx.mock(assert_all_called=True) as mock:
        mock.put(CHANGE_PC_URL).mock(
            return_value=httpx.Response(200, headers={"x-customer-wh": "4701"})
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("35001")

    assert warehouse == "4701"


async def test_resolve_warehouse_returns_none_on_404_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RF-9, regression for Decision D5: a 404 (postal code without
    service, real body verified live on 2026-09-24) is NOT retried."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.scrapers.mercadona_client.asyncio.sleep", sleep_mock)

    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(
            return_value=httpx.Response(
                404, json={"error_msg": "This zip code is outside of our working area"}
            )
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("99999")

    assert warehouse is None
    assert route.call_count == 1
    sleep_mock.assert_not_awaited()


async def test_resolve_warehouse_recovers_on_third_attempt_after_two_5xx() -> None:
    """RF-8: a transient 5xx is retried, same policy as spec 002."""
    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, headers={"x-customer-wh": "mad3"}),
            ]
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("28001")

    assert warehouse == "mad3"
    assert route.call_count == 3


async def test_resolve_warehouse_raises_after_exhausting_retries_on_persistent_5xx() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)]
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            with pytest.raises(httpx.HTTPStatusError):
                await client.resolve_warehouse("28001")

    assert route.call_count == 3


async def test_resolve_warehouse_recovers_on_429_with_retry_after() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, headers={"x-customer-wh": "vlc1"}),
            ]
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("46001")

    assert warehouse == "vlc1"
    assert route.call_count == 2


async def test_resolve_warehouse_raises_warehouse_header_missing_and_logs_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RF-10, RF-12: a 2xx without x-customer-wh is not observed live but
    would signal a broken upstream contract — surfaced, not silently
    treated as "not served" (RF-9), and never logs Set-Cookie or other
    unrelated headers."""
    with respx.mock(assert_all_called=True) as mock:
        mock.put(CHANGE_PC_URL).mock(
            return_value=httpx.Response(200, headers={"Set-Cookie": "session=abc123"})
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            with caplog.at_level(logging.WARNING):
                with pytest.raises(WarehouseHeaderMissing):
                    await client.resolve_warehouse("28001")

    warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_logs) == 1
    for record in warning_logs:
        message = record.getMessage()
        assert "session=abc123" not in message
        assert "Set-Cookie" not in message


async def test_resolve_warehouse_does_not_retry_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """RF-13 regression: a 4xx other than 404/429 (e.g. a WAF block) is
    NOT retried — same non-retry contract as any other non-429 4xx
    (Decision D5). Mapping to 502 is done by the resolver in T6."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr("app.scrapers.mercadona_client.asyncio.sleep", sleep_mock)

    with respx.mock(assert_all_called=True) as mock:
        route = mock.put(CHANGE_PC_URL).mock(return_value=httpx.Response(403))
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            with pytest.raises(httpx.HTTPStatusError):
                await client.resolve_warehouse("28001")

    assert route.call_count == 1
    sleep_mock.assert_not_awaited()
