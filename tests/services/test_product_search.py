"""T11/T12 — product_search.search_products: cache-hit returns the cached
response directly without touching MercadonaClient; cache-miss fetches,
maps, caches, and returns the fresh result (RF-1, RF-4).

T10 — 007-mercadona-scraper-warehouse-resolution: the cache key is keyed
by warehouse, not postal_code (RF-6, Decision D8 in plan.md), so a cache
hit rewrites SearchMeta.postal_code to the current request's postal_code
instead of leaking a different postal_code that happens to share the same
warehouse (RF-7)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

from app.core.config import Settings
from app.models.mercadona_raw import RawAlgoliaProduct
from app.models.product import ProductOut, ProductSearchResponse, SearchMeta
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products

ALGOLIA_FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"
)


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


def _raw_algolia_product() -> RawAlgoliaProduct:
    payload = json.loads(ALGOLIA_FIXTURE_PATH.read_text(encoding="utf-8"))
    return RawAlgoliaProduct.model_validate(payload)


def _sample_response() -> ProductSearchResponse:
    return ProductSearchResponse(
        search=SearchMeta(
            postal_code="28001",
            term="leche",
            warehouse="mad1",
            strategy_used="api",
            scraped_at=datetime.now(UTC),
            total_results=1,
        ),
        products=[
            ProductOut(
                id="1",
                name="Leche entera",
                price=1.05,
                price_format="1.05 €/L",
                image_url="https://example.com/1.jpg",
                category="Lácteos",
            )
        ],
    )


async def test_returns_cached_response_without_calling_client() -> None:
    cached_response = _sample_response()
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = cached_response
    client = AsyncMock(spec=MercadonaClient)
    query = ProductQuery(postal_code="28001", term="leche")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    assert result == cached_response
    cache.get.assert_awaited_once_with("search:mad1:leche")
    client.search.assert_not_called()


async def test_shared_warehouse_cache_hit_rewrites_postal_code_to_current_request() -> None:
    """RF-7: two postal codes resolving to the same warehouse share the
    product cache entry (RF-6), but the response must always reflect the
    postal_code of the CURRENT request, not whichever one wrote the cache
    first."""
    cached_response = _sample_response()
    assert cached_response.search.postal_code == "28001"
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = cached_response
    client = AsyncMock(spec=MercadonaClient)
    query = ProductQuery(postal_code="28002", term="leche")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    assert result.search.postal_code == "28002"
    assert result.search.warehouse == "mad1"
    assert result.products == cached_response.products
    cache.get.assert_awaited_once_with("search:mad1:leche")


async def test_cache_miss_fetches_maps_and_caches_result() -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = [_raw_algolia_product()]
    query = ProductQuery(postal_code="28001", term="leche")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    client.search.assert_awaited_once_with(term="leche", warehouse="mad1")
    assert result.search.postal_code == "28001"
    assert result.search.term == "leche"
    assert result.search.warehouse == "mad1"
    assert result.search.total_results == 1
    assert len(result.products) == 1
    assert result.products[0].id == "10381"
    assert result.products[0].name == "Leche semidesnatada Hacendado"

    cache.set.assert_awaited_once_with("search:mad1:leche", result, ttl=3600)
