"""T6 — resolve_warehouse (app/services/warehouse_resolver.py) orchestrates
WarehouseCacheRepository and MercadonaClient.resolve_warehouse: cache hits
(positive or negative) short-circuit the client call (RF-4, RF-11); a miss
calls the client and writes the result back to cache with the right TTL;
any upstream failure — including the 404-derived "not served" case (RF-9)
— becomes either PostalCodeNotServedError or UpstreamUnavailableError,
never a raw httpx/client exception (RF-8, RF-9, RF-10, RF-13, Decision D1
in plan.md)."""

import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.exceptions import PostalCodeNotServedError, UpstreamUnavailableError
from app.scrapers.mercadona_client import MercadonaClient, WarehouseHeaderMissing
from app.services.cache import CachedWarehouse, WarehouseCacheRepository
from app.services.warehouse_resolver import resolve_warehouse


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        WAREHOUSE_CACHE_TTL_SECONDS=86400,
        WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS=3600,
    )


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "PUT", "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"
    )
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Server error '{status_code}'", request=request, response=response
    )


async def test_cache_miss_resolves_via_client_and_writes_positive_cache(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad3"

    with caplog.at_level(logging.INFO):
        warehouse = await resolve_warehouse("28001", cache, client, _settings())

    assert warehouse == "mad3"
    cache.set_served.assert_awaited_once_with("28001", "mad3", ttl=86400)
    cache.set_not_served.assert_not_called()
    assert any(record.levelno == logging.INFO for record in caplog.records)


async def test_positive_cache_hit_skips_client_call(caplog: pytest.LogCaptureFixture) -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = CachedWarehouse("mad3")
    client = AsyncMock(spec=MercadonaClient)

    with caplog.at_level(logging.INFO):
        warehouse = await resolve_warehouse("28001", cache, client, _settings())

    assert warehouse == "mad3"
    client.resolve_warehouse.assert_not_called()
    assert any(record.levelno == logging.INFO for record in caplog.records)


async def test_client_returns_none_raises_not_served_and_writes_negative_cache() -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = None

    with pytest.raises(PostalCodeNotServedError):
        await resolve_warehouse("99999", cache, client, _settings())

    cache.set_not_served.assert_awaited_once_with("99999", ttl=3600)
    cache.set_served.assert_not_called()


async def test_negative_cache_hit_raises_not_served_without_calling_client() -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = CachedWarehouse(None)
    client = AsyncMock(spec=MercadonaClient)

    with pytest.raises(PostalCodeNotServedError):
        await resolve_warehouse("99999", cache, client, _settings())

    client.resolve_warehouse.assert_not_called()


@pytest.mark.parametrize(
    "client_error",
    [
        httpx.ConnectError("boom"),
        _http_status_error(503),
        _http_status_error(429),
        _http_status_error(403),
    ],
)
async def test_client_upstream_failure_raises_upstream_unavailable_without_caching(
    client_error: Exception,
) -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.side_effect = client_error

    with pytest.raises(UpstreamUnavailableError):
        await resolve_warehouse("28001", cache, client, _settings())

    cache.set_served.assert_not_called()
    cache.set_not_served.assert_not_called()


async def test_warehouse_header_missing_raises_upstream_unavailable_without_caching() -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.side_effect = WarehouseHeaderMissing(
        "Mercadona's change-pc responded 2xx without x-customer-wh"
    )

    with pytest.raises(UpstreamUnavailableError):
        await resolve_warehouse("28001", cache, client, _settings())

    cache.set_served.assert_not_called()
    cache.set_not_served.assert_not_called()


async def test_logs_never_leak_cookies_or_upstream_error_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cache = AsyncMock(spec=WarehouseCacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad3"

    with caplog.at_level(logging.INFO):
        await resolve_warehouse("28001", cache, client, _settings())

    for record in caplog.records:
        message = record.getMessage()
        assert "Set-Cookie" not in message
        assert "error_msg" not in message
