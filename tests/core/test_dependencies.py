"""T2 — 006-mercadona-scraper-refactor: get_settings/get_cache_repository/
get_mercadona_client centralize what app/api/v1/products.py and
app/core/security.py used to define separately — same behavior (read
straight from app.state), now in one place with a typed view via
AppState (plan.md Decisions D3/D4)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.core.dependencies import (
    get_cache_repository,
    get_mercadona_client,
    get_settings,
    get_warehouse_cache_repository,
)
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository, WarehouseCacheRepository


def _make_request(
    settings: Settings,
    cache_repository: object,
    mercadona_client: object,
    warehouse_cache_repository: object = None,
):
    state = SimpleNamespace(
        settings=settings,
        cache_repository=cache_repository,
        mercadona_client=mercadona_client,
        warehouse_cache_repository=warehouse_cache_repository,
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_get_settings_returns_the_exact_object_on_app_state() -> None:
    settings = Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es", REDIS_URL="redis://localhost:6379/0"
    )
    request = _make_request(settings, MagicMock(), AsyncMock())

    assert get_settings(request) is settings


def test_get_cache_repository_returns_the_exact_object_on_app_state() -> None:
    cache_repository = MagicMock(spec=CacheRepository)
    request = _make_request(MagicMock(), cache_repository, AsyncMock())

    assert get_cache_repository(request) is cache_repository


def test_get_mercadona_client_returns_the_exact_object_on_app_state() -> None:
    mercadona_client = AsyncMock(spec=MercadonaClient)
    request = _make_request(MagicMock(), MagicMock(), mercadona_client)

    assert get_mercadona_client(request) is mercadona_client


def test_get_warehouse_cache_repository_returns_the_exact_object_on_app_state() -> None:
    """T8 — 007-mercadona-scraper-warehouse-resolution, Decision D2 in
    plan.md: same pattern as get_cache_repository."""
    warehouse_cache_repository = MagicMock(spec=WarehouseCacheRepository)
    request = _make_request(
        MagicMock(),
        MagicMock(),
        AsyncMock(),
        warehouse_cache_repository=warehouse_cache_repository,
    )

    assert get_warehouse_cache_repository(request) is warehouse_cache_repository
