"""T14/T16 — GET /api/v1/products: happy path returns 200 with parsed
results (RF-1); a term with no matches returns 200 with an empty list,
not an error (RF-2)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.products import get_cache_repository, get_mercadona_client, get_settings, router
from app.core.config import Settings
from app.models.mercadona_raw import RawAlgoliaProduct
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository

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


async def test_get_products_returns_200_with_results(app: FastAPI) -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = [_raw_algolia_product()]

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()

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
    client.search.return_value = []

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: _settings()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "xyz-no-existe"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["products"] == []
    assert body["search"]["total_results"] == 0
