from datetime import UTC, datetime

import httpx

from app.core.config import Settings
from app.exceptions import UpstreamUnavailableError
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
    # plan.md): two postal codes resolving to the same warehouse must
    # share this cache entry, and two resolving to different warehouses
    # must never collide.
    cache_key = f"search:{warehouse}:{query.term}"
    cached = await cache.get(cache_key)
    if cached is not None:
        # RF-7: the cache entry may have been written by a different
        # postal_code that shares this warehouse — the response must
        # always reflect the postal_code of THIS request.
        return cached.model_copy(
            update={"search": cached.search.model_copy(update={"postal_code": query.postal_code})}
        )

    try:
        raw_products = await client.search(term=query.term, warehouse=warehouse)
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError("Mercadona/Algolia is unreachable") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code >= 500 or exc.response.status_code == 429:
            raise UpstreamUnavailableError(
                f"Mercadona/Algolia returned {exc.response.status_code}"
            ) from exc
        raise
    products = [map_raw_algolia_product_to_product_out(raw) for raw in raw_products]
    response = ProductSearchResponse(
        search=SearchMeta(
            postal_code=query.postal_code,
            term=query.term,
            warehouse=warehouse,
            strategy_used=_STRATEGY_USED,
            scraped_at=datetime.now(UTC),
            total_results=len(products),
        ),
        products=products,
    )

    await cache.set(cache_key, response, ttl=settings.CACHE_TTL_SECONDS)
    return response
