import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import Settings
from app.core.dependencies import (
    get_cache_repository,
    get_mercadona_client,
    get_settings,
    get_warehouse_cache_repository,
)
from app.exceptions import PostalCodeNotServedError, UpstreamUnavailableError
from app.models.product import ProductSearchResponse
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository
from app.services.product_search import search_products
from app.services.warehouse_resolver import resolve_warehouse

__all__ = [
    "get_cache_repository",
    "get_mercadona_client",
    "get_settings",
    "get_warehouse_cache_repository",
    "router",
]

logger = logging.getLogger(__name__)

router = APIRouter()


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[CacheRepository, Depends(get_cache_repository)]
MercadonaClientDep = Annotated[MercadonaClient, Depends(get_mercadona_client)]
WarehouseCacheDep = Annotated[WarehouseCacheRepository, Depends(get_warehouse_cache_repository)]


@router.get(
    "/products",
    responses={
        404: {"description": "Postal code is outside Mercadona's service area"},
        502: {"description": "Mercadona/Algolia is unavailable after retrying"},
    },
)
async def get_products(
    query: Annotated[ProductQuery, Query()],
    settings: SettingsDep,
    cache: CacheDep,
    client: MercadonaClientDep,
    warehouse_cache: WarehouseCacheDep,
) -> ProductSearchResponse:
    try:
        warehouse = await resolve_warehouse(query.postal_code, warehouse_cache, client, settings)
        return await search_products(
            query, warehouse=warehouse, cache=cache, client=client, settings=settings
        )
    except PostalCodeNotServedError as exc:
        raise HTTPException(status_code=404, detail="Postal code not served by Mercadona") from exc
    except UpstreamUnavailableError as exc:
        logger.exception(
            "Upstream unavailable for postal_code=%s term=%s", query.postal_code, query.term
        )
        raise HTTPException(status_code=502, detail="Mercadona is currently unavailable") from exc
