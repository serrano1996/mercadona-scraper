"""T11 — product_search.search_products returns the cached response
directly on a cache hit, without touching MercadonaClient."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.models.product import ProductOut, ProductSearchResponse, SearchMeta
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products


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

    result = await search_products(query, warehouse="mad1", cache=cache, client=client)

    assert result == cached_response
    cache.get.assert_awaited_once_with("search:28001:leche")
    client.search.assert_not_called()
