"""T7 — 004-mercadona-scraper-authentication: a request without a valid
X-API-Key never reaches business logic — no HTTP call to Mercadona/Algolia
goes out, and the cache is never touched (spec.md RF-1). Complements T5's
unit-level test (tests/test_main.py, dependency_overrides) with an
integration-level check against the real MercadonaClient/CacheRepository
wired by the real lifespan."""

from unittest.mock import AsyncMock

import pytest
import respx
from httpx import AsyncClient

from app.services.cache import CacheRepository

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"


async def test_missing_header_never_calls_upstream_or_cache(
    client: AsyncClient, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_route = respx_mock.get(MANIFEST_URL)
    cache_get_spy = AsyncMock(wraps=CacheRepository.get)
    monkeypatch.setattr(CacheRepository, "get", cache_get_spy)

    response = await client.get(
        "/api/v1/products",
        params={"postal_code": "28001", "term": "leche"},
        headers={"X-API-Key": ""},
    )

    assert response.status_code == 401
    assert manifest_route.call_count == 0
    cache_get_spy.assert_not_called()


async def test_invalid_token_never_calls_upstream_or_cache(
    client: AsyncClient, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_route = respx_mock.get(MANIFEST_URL)
    cache_get_spy = AsyncMock(wraps=CacheRepository.get)
    monkeypatch.setattr(CacheRepository, "get", cache_get_spy)

    response = await client.get(
        "/api/v1/products",
        params={"postal_code": "28001", "term": "leche"},
        headers={"X-API-Key": "not-the-configured-token"},
    )

    assert response.status_code == 401
    assert manifest_route.call_count == 0
    cache_get_spy.assert_not_called()
