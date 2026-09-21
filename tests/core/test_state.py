"""T1 — 006-mercadona-scraper-refactor: AppState is a plain typed
container for the objects the lifespan stores on app.state (spec.md
soporte de RF-6)."""

from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.core.state import AppState
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository


def test_app_state_exposes_the_three_fields_as_given() -> None:
    settings = Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es", REDIS_URL="redis://localhost:6379/0"
    )
    cache_repository = MagicMock(spec=CacheRepository)
    mercadona_client = AsyncMock(spec=MercadonaClient)

    state = AppState(
        settings=settings, cache_repository=cache_repository, mercadona_client=mercadona_client
    )

    assert state.settings is settings
    assert state.cache_repository is cache_repository
    assert state.mercadona_client is mercadona_client
