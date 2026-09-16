from app.models.product import ProductSearchResponse
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository


async def search_products(
    query: ProductQuery,
    warehouse: str,
    cache: CacheRepository,
    client: MercadonaClient,
) -> ProductSearchResponse:
    cache_key = f"search:{query.postal_code}:{query.term}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    # Cache-miss path (fetch + map + cache-write) implemented in T12.
    raise NotImplementedError("cache-miss path implemented in T12")
