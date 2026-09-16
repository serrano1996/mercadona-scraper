from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.models.product import ProductSearchResponse
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products

router = APIRouter()

# Provisional: real postal_code -> warehouse resolution isn't built yet
# (see Decision D8 in plan.md). Every request resolves to the same
# warehouse for the MVP.
_DEFAULT_WAREHOUSE = "mad1"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_cache_repository(request: Request) -> CacheRepository:
    return request.app.state.cache_repository


def get_mercadona_client(request: Request) -> MercadonaClient:
    return request.app.state.mercadona_client


SettingsDep = Annotated[Settings, Depends(get_settings)]
CacheDep = Annotated[CacheRepository, Depends(get_cache_repository)]
MercadonaClientDep = Annotated[MercadonaClient, Depends(get_mercadona_client)]


@router.get("/products")
async def get_products(
    postal_code: str,
    term: str,
    settings: SettingsDep,
    cache: CacheDep,
    client: MercadonaClientDep,
) -> ProductSearchResponse:
    query = ProductQuery(postal_code=postal_code, term=term)
    return await search_products(
        query, warehouse=_DEFAULT_WAREHOUSE, cache=cache, client=client, settings=settings
    )
