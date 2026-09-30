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

import pytest

from app.core.config import Settings
from app.exceptions import PageOutOfRangeError
from app.models.mercadona_raw import RawAlgoliaProduct
from app.models.product import ProductOut, ProductSearchResponse, SearchMeta
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products
from tests.fixtures.algolia import search_result

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
            page=1,
            page_size=50,
            total_pages=1,
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
    cache.get.assert_awaited_once_with("search:mad1:leche:1:50")
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
    cache.get.assert_awaited_once_with("search:mad1:leche:1:50")


async def test_cache_miss_fetches_maps_and_caches_result() -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = search_result([_raw_algolia_product()])
    query = ProductQuery(postal_code="28001", term="leche")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    client.search.assert_awaited_once_with(term="leche", warehouse="mad1", page=1, page_size=50)
    assert result.search.postal_code == "28001"
    assert result.search.term == "leche"
    assert result.search.warehouse == "mad1"
    assert result.search.total_results == 1
    assert len(result.products) == 1
    assert result.products[0].id == "10381"
    assert result.products[0].name == "Leche semidesnatada Hacendado"

    cache.set.assert_awaited_once_with("search:mad1:leche:1:50", result, ttl=3600)


async def test_reports_real_total_and_page_fields() -> None:
    """T8 — 008-mercadona-scraper-search-completeness, RF-6/RF-7: the
    response reports Algolia's real total (233 for "leche", verified live)
    and page count, not the number of products in this page."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = search_result(
        [_raw_algolia_product()] * 50, nb_hits=233, nb_pages=5
    )
    query = ProductQuery(postal_code="28001", term="leche")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    assert result.search.total_results == 233
    assert result.search.total_pages == 5
    assert result.search.page == 1
    assert result.search.page_size == 50
    assert len(result.products) == 50


async def test_cache_key_includes_page_and_page_size() -> None:
    """T8 — RF-10: each page is cached separately."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = search_result([_raw_algolia_product()], nb_hits=233, nb_pages=5)
    query = ProductQuery(postal_code="28001", term="leche", page=2, page_size=20)

    await search_products(query, warehouse="mad1", cache=cache, client=client, settings=_settings())

    cache.get.assert_awaited_once_with("search:mad1:leche:2:20")


async def test_empty_page_beyond_the_first_raises_page_out_of_range_without_caching() -> None:
    """T8 — RF-9, Decision D4: Algolia answers an out-of-range page with
    no hits and nbHits 0 (verified live with page=99), so nbHits can't
    tell "no results" from "past the last page" — an empty page > 1 is
    out of range, and that answer is never cached."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = search_result([], nb_hits=0, nb_pages=0)
    query = ProductQuery(postal_code="28001", term="leche", page=6)

    with pytest.raises(PageOutOfRangeError):
        await search_products(
            query, warehouse="mad1", cache=cache, client=client, settings=_settings()
        )

    cache.set.assert_not_called()


async def test_empty_first_page_is_still_a_normal_empty_result() -> None:
    """T8 — regression of spec 001 RF-2: page 1 with no matches is a 200
    with an empty list, not an out-of-range page."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.return_value = search_result([], nb_hits=0, nb_pages=0)
    query = ProductQuery(postal_code="28001", term="xyz-no-existe")

    result = await search_products(
        query, warehouse="mad1", cache=cache, client=client, settings=_settings()
    )

    assert result.products == []
    assert result.search.total_results == 0
