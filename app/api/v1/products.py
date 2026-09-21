import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings
from app.core.dependencies import get_cache_repository, get_mercadona_client, get_settings
from app.exceptions import UpstreamUnavailableError
from app.models.product import ProductSearchResponse
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products

__all__ = [
    "get_cache_repository",
    "get_mercadona_client",
    "get_settings",
    "router",
]

logger = logging.getLogger(__name__)

router = APIRouter()

# Provisional: real postal_code -> warehouse resolution isn't built yet
# (see Decision D8 in plan.md). Every request resolves to the same
# warehouse for the MVP.
_DEFAULT_WAREHOUSE = "mad1"


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[CacheRepository, Depends(get_cache_repository)]
MercadonaClientDep = Annotated[MercadonaClient, Depends(get_mercadona_client)]


@router.get(
    "/products",
    responses={502: {"description": "Mercadona/Algolia is unavailable after retrying"}},
)
async def get_products(
    postal_code: str,
    term: str,
    settings: SettingsDep,
    cache: CacheDep,
    client: MercadonaClientDep,
) -> ProductSearchResponse:
    query = ProductQuery(postal_code=postal_code, term=term)
    try:
        return await search_products(
            query, warehouse=_DEFAULT_WAREHOUSE, cache=cache, client=client, settings=settings
        )
    except UpstreamUnavailableError as exc:
        logger.exception("Upstream unavailable for postal_code=%s term=%s", postal_code, term)
        raise HTTPException(status_code=502, detail="Mercadona is currently unavailable") from exc
