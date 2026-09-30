from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.exceptions import PageOutOfRangeError, UpstreamUnavailableError
from app.mappers.product_mapper import map_raw_algolia_product_to_product_out
from app.models.product import ProductSearchResponse, SearchMeta
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository

_STRATEGY_USED = "algolia"


async def search_products(
    query: ProductQuery,
    warehouse: str,
    cache: CacheRepository,
    client: MercadonaClient,
    settings: Settings,
) -> ProductSearchResponse:
    # Keyed by warehouse, not postal_code (spec 007 RF-6, Decision D8 in
    # plan.md 007): two postal codes resolving to the same warehouse must
    # share this cache entry, and two resolving to different warehouses
    # must never collide. Page and page_size are part of the key (spec 008
    # RF-10); the format change also stops pre-008 entries, which lack the
    # page fields, from ever being read back (Decision D5 in plan.md 008).
    cache_key = f"search:{warehouse}:{query.term}:{query.page}:{query.page_size}"
    cached = await cache.get(cache_key)
    if cached is not None:
        # RF-7: the cache entry may have been written by a different
        # postal_code that shares this warehouse — the response must
        # always reflect the postal_code of THIS request.
        return cached.model_copy(
            update={"search": cached.search.model_copy(update={"postal_code": query.postal_code})}
        )

    try:
        result = await client.search(
            term=query.term, warehouse=warehouse, page=query.page, page_size=query.page_size
        )
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError("Mercadona/Algolia is unreachable") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500 or exc.response.status_code == 429:
            raise UpstreamUnavailableError(
                f"Mercadona/Algolia returned {exc.response.status_code}"
            ) from exc
        raise
    if query.page > 1 and not result.hits:
        # Algolia answers an out-of-range page with nbHits 0, so the total
        # can't tell "no results" from "past the last page" (spec 008 RF-9,
        # Decision D4). Raised before caching: never cache this answer.
        raise PageOutOfRangeError(f"page {query.page} is out of range")
    products = [map_raw_algolia_product_to_product_out(raw) for raw in result.hits]
    response = ProductSearchResponse(
        search=SearchMeta(
            postal_code=query.postal_code,
            term=query.term,
            warehouse=warehouse,
            strategy_used=_STRATEGY_USED,
            scraped_at=datetime.now(UTC),
            total_results=result.nbHits,
            page=query.page,
            page_size=query.page_size,
            total_pages=result.nbPages,
        ),
        products=products,
    )

    await cache.set(cache_key, response, ttl=settings.CACHE_TTL_SECONDS)
    return response
