"""Typed shape of app.state (spec 006-mercadona-scraper-refactor) — the
lifespan (app/main.py) keeps assigning app.state.* exactly as before;
this only gives app/core/dependencies.py a typed view of that state via
typing.cast, with zero runtime behavior change.
"""

from dataclasses import dataclass

from app.core.config import Settings
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository


@dataclass
class AppState:
    settings: Settings
    cache_repository: CacheRepository
    mercadona_client: MercadonaClient
    warehouse_cache_repository: WarehouseCacheRepository
