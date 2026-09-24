"""T15 — GET /api/v1/products maps UpstreamUnavailableError to 502 (RF-3).

test_get_products_logs_error_when_upstream_unavailable (T9, spec 003) —
that translation also leaves an ERROR log line with postal_code/term
context (spec.md RF-3)."""

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.products import (
    get_cache_repository,
    get_mercadona_client,
    get_settings,
    get_warehouse_cache_repository,
    router,
)
from app.core.config import Settings
from app.exceptions import UpstreamUnavailableError
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


def _warehouse_cache_miss() -> AsyncMock:
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)
    warehouse_cache.get.return_value = None
    return warehouse_cache


async def test_get_products_returns_502_when_upstream_unavailable(app: FastAPI) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad1"
    client.search.side_effect = UpstreamUnavailableError("Mercadona/Algolia returned 503")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
        )

    assert response.status_code == 502


async def test_get_products_logs_error_when_upstream_unavailable(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad1"
    client.search.side_effect = UpstreamUnavailableError("Mercadona/Algolia returned 503")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    with caplog.at_level(logging.ERROR):
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            response = await http_client.get(
                "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
            )

    assert response.status_code == 502
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_logs) == 1
    message = error_logs[0].getMessage()
    assert "28001" in message
    assert "leche" in message


async def test_get_products_returns_404_when_postal_code_not_served(app: FastAPI) -> None:
    """T9 — RF-9: PostalCodeNotServedError during warehouse resolution
    becomes a 404 with our own detail, never Mercadona's error_msg, and
    MercadonaClient.search is never called."""
    cache = AsyncMock(spec=CacheRepository)
    client = AsyncMock(spec=MercadonaClient)
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)
    warehouse_cache.get.return_value = None
    client.resolve_warehouse.return_value = None

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = lambda: warehouse_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "99999", "term": "leche"}
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Postal code not served by Mercadona"}
    client.search.assert_not_called()


async def test_get_products_returns_502_when_resolution_upstream_unavailable(
    app: FastAPI,
) -> None:
    """T9 — RF-8/RF-13: an upstream failure resolving the warehouse (not
    searching) also maps to 502, and search is never reached."""
    cache = AsyncMock(spec=CacheRepository)
    client = AsyncMock(spec=MercadonaClient)
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)
    warehouse_cache.get.return_value = None
    client.resolve_warehouse.side_effect = UpstreamUnavailableError("Mercadona returned 503")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = lambda: warehouse_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
        )

    assert response.status_code == 502
    client.search.assert_not_called()
