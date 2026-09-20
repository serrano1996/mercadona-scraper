"""T15 — GET /api/v1/products maps UpstreamUnavailableError to 502 (RF-3).

test_get_products_logs_error_when_upstream_unavailable (T9, spec 003) —
that translation also leaves an ERROR log line with postal_code/term
context (spec.md RF-3)."""

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.products import get_cache_repository, get_mercadona_client, get_settings, router
from app.core.config import Settings
from app.exceptions import UpstreamUnavailableError
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository


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


async def test_get_products_returns_502_when_upstream_unavailable(app: FastAPI) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = UpstreamUnavailableError("Mercadona/Algolia returned 503")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()

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
    client.search.side_effect = UpstreamUnavailableError("Mercadona/Algolia returned 503")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()

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
