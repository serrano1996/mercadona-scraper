"""Resolves a postal_code to its Mercadona warehouse, orchestrating
WarehouseCacheRepository and MercadonaClient.resolve_warehouse (spec 007,
Decision D1 in plan.md). Kept separate from MercadonaClient: the client
only knows how to talk to Mercadona (Decision D1), this module owns the
cache-then-network policy and the translation into domain exceptions, the
same split product_search.py already applies to CacheRepository/search()."""

import logging

import httpx

from app.core.config import Settings
from app.exceptions import PostalCodeNotServedError, UpstreamUnavailableError
from app.scrapers.mercadona_client import MercadonaClient, WarehouseHeaderMissing
from app.services.cache import WarehouseCacheRepository

logger = logging.getLogger(__name__)


async def resolve_warehouse(
    postal_code: str,
    cache: WarehouseCacheRepository,
    client: MercadonaClient,
    settings: Settings,
) -> str:
    cached = await cache.get(postal_code)
    if cached is not None:
        if cached.warehouse is None:
            logger.info("Warehouse cache hit (not served) for postal_code=%s", postal_code)
            raise PostalCodeNotServedError(f"postal_code {postal_code} has no Mercadona warehouse")
        logger.info(
            "Warehouse cache hit for postal_code=%s: warehouse=%s", postal_code, cached.warehouse
        )
        return cached.warehouse

    try:
        warehouse = await client.resolve_warehouse(postal_code)
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError("Mercadona is unreachable") from exc
    except httpx.HTTPStatusError as exc:
        # 404 (not served) never reaches here — MercadonaClient.resolve_warehouse
        # already returns None for it. Any HTTPStatusError that does
        # propagate is a genuine upstream failure: exhausted 5xx/429
        # retries, or another 4xx like 403 (RF-8, RF-13).
        raise UpstreamUnavailableError(f"Mercadona returned {exc.response.status_code}") from exc
    except WarehouseHeaderMissing as exc:
        raise UpstreamUnavailableError("Mercadona's change-pc response is malformed") from exc

    if warehouse is None:
        logger.warning("Mercadona has no warehouse for postal_code=%s", postal_code)
        await cache.set_not_served(postal_code, ttl=settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS)
        raise PostalCodeNotServedError(f"postal_code {postal_code} has no Mercadona warehouse")

    logger.info("Resolved postal_code=%s to warehouse=%s", postal_code, warehouse)
    await cache.set_served(postal_code, warehouse, ttl=settings.WAREHOUSE_CACHE_TTL_SECONDS)
    return warehouse
