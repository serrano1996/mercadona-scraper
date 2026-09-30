"""T14/T16 — GET /api/v1/products: happy path returns 200 with parsed
results (RF-1); a term with no matches returns 200 with an empty list,
not an error (RF-2)."""

import json
from pathlib import Path
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
from app.models.mercadona_raw import RawAlgoliaProduct
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository
from tests.fixtures.algolia import search_result

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


def _raw_algolia_product() -> RawAlgoliaProduct:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return RawAlgoliaProduct.model_validate(payload)


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


def _warehouse_cache_miss() -> AsyncMock:
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)
    warehouse_cache.get.return_value = None
    return warehouse_cache


async def test_get_products_returns_200_with_results(app: FastAPI) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad1"
    client.search.return_value = search_result([_raw_algolia_product()])

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["search"]["postal_code"] == "28001"
    assert body["search"]["term"] == "leche"
    assert len(body["products"]) == 1
    assert body["products"][0]["id"] == "10381"


async def test_get_products_returns_200_with_empty_list_when_no_matches(app: FastAPI) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad1"
    client.search.return_value = search_result([])

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "xyz-no-existe"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["products"] == []
    assert body["search"]["total_results"] == 0


async def test_get_products_passes_resolved_warehouse_to_search(app: FastAPI) -> None:
    """T9 — 007-mercadona-scraper-warehouse-resolution, RF-5: the resolved
    warehouse (not a hardcoded default) reaches MercadonaClient.search."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "vlc1"
    client.search.return_value = search_result([])

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        await http_client.get("/api/v1/products", params={"postal_code": "46001", "term": "leche"})

    client.search.assert_awaited_once_with(term="leche", warehouse="vlc1", page=1, page_size=50)


async def test_get_products_rejects_invalid_postal_code_without_calling_mercadona(
    app: FastAPI,
) -> None:
    """T9 — RF-1: FastAPI validates ProductQuery from the route signature
    (Decision D7 in plan.md), so an invalid postal_code never reaches
    MercadonaClient/WarehouseCacheRepository."""
    cache = AsyncMock(spec=CacheRepository)
    client = AsyncMock(spec=MercadonaClient)
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = lambda: warehouse_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "1234", "term": "leche"}
        )

    assert response.status_code == 422
    client.resolve_warehouse.assert_not_called()
    client.search.assert_not_called()
    warehouse_cache.get.assert_not_called()


async def test_get_products_rejects_blank_term_without_calling_mercadona(app: FastAPI) -> None:
    """T2 — 008-mercadona-scraper-search-completeness, RF-1: a blank term
    is rejected by ProductQuery validation at the route boundary (Decision
    D1 in plan.md), before warehouse resolution or search."""
    cache = AsyncMock(spec=CacheRepository)
    client = AsyncMock(spec=MercadonaClient)
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = lambda: warehouse_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "  "}
        )

    assert response.status_code == 422
    client.resolve_warehouse.assert_not_called()
    client.search.assert_not_called()


async def test_get_products_searches_and_reports_the_normalized_term(app: FastAPI) -> None:
    """T2 — RF-3/RF-4: the route searches with the normalized term and
    reports that same term back in SearchMeta.term."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.resolve_warehouse.return_value = "mad1"
    client.search.return_value = search_result([])

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = _warehouse_cache_miss

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "Leche "}
        )

    assert response.status_code == 200
    client.search.assert_awaited_once_with(term="leche", warehouse="mad1", page=1, page_size=50)
    assert response.json()["search"]["term"] == "leche"


async def test_get_products_rejects_oversized_page_without_calling_mercadona(
    app: FastAPI,
) -> None:
    """T6 — 008-mercadona-scraper-search-completeness, RF-5: page_size
    over 100 is rejected at the route boundary, before any upstream call."""
    cache = AsyncMock(spec=CacheRepository)
    client = AsyncMock(spec=MercadonaClient)
    warehouse_cache = AsyncMock(spec=WarehouseCacheRepository)

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[get_warehouse_cache_repository] = lambda: warehouse_cache

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products",
            params={"postal_code": "28001", "term": "leche", "page_size": 101},
        )

    assert response.status_code == 422
    client.resolve_warehouse.assert_not_called()
    client.search.assert_not_called()
