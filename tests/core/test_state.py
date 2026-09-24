"""T1 — 006-mercadona-scraper-refactor: AppState is a plain typed
container for the objects the lifespan stores on app.state (spec.md
soporte de RF-6). Extended in T8 (007-mercadona-scraper-warehouse-
resolution) with warehouse_cache_repository (Decision D2 in plan.md)."""

from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.core.state import AppState
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository


def test_app_state_exposes_the_four_fields_as_given() -> None:
    settings = Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es", REDIS_URL="redis://localhost:6379/0"
    )
    cache_repository = MagicMock(spec=CacheRepository)
    mercadona_client = AsyncMock(spec=MercadonaClient)
    warehouse_cache_repository = MagicMock(spec=WarehouseCacheRepository)

    state = AppState(
        settings=settings,
        cache_repository=cache_repository,
        mercadona_client=mercadona_client,
        warehouse_cache_repository=warehouse_cache_repository,
    )

    assert state.settings is settings
    assert state.cache_repository is cache_repository
    assert state.mercadona_client is mercadona_client
    assert state.warehouse_cache_repository is warehouse_cache_repository
