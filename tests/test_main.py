"""T17 — main.py assembles FastAPI, mounts the products router, and its
lifespan wires httpx/redis clients into app.state for the route
dependencies (app/api/v1/products.py) to read."""

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.products import get_cache_repository, get_mercadona_client, get_settings
from app.core.config import Settings
from app.main import app
from app.scrapers.http_client_factory import USER_AGENTS
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository

# T6 — 004-mercadona-scraper-authentication: shared valid token for tests
# that need to get past auth to exercise what they actually test.
# test_products_router_requires_api_key deliberately does NOT use this.
TEST_API_KEY = "test-main-api-key"


@pytest.fixture(autouse=True)
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCADONA_BASE_URL", "https://tienda.mercadona.es")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("API_KEYS", TEST_API_KEY)


def test_docs_load() -> None:
    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200


def test_openapi_schema_includes_product_search_response() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    schema = response.json()
    assert "ProductSearchResponse" in schema["components"]["schemas"]


def test_lifespan_populates_app_state() -> None:
    with TestClient(app):
        assert app.state.settings.MERCADONA_BASE_URL == "https://tienda.mercadona.es"
        assert app.state.cache_repository is not None
        assert app.state.mercadona_client is not None
        assert app.state.warehouse_cache_repository is not None


def test_lifespan_wires_warehouse_cache_repository_on_the_same_redis_client() -> None:
    """T8 — 007-mercadona-scraper-warehouse-resolution, Decision D2 in
    plan.md: WarehouseCacheRepository shares the same Redis connection as
    CacheRepository, no separate connection pool."""
    with TestClient(app):
        assert app.state.warehouse_cache_repository._redis is app.state.cache_repository._redis


def test_mercadona_client_uses_a_pooled_user_agent() -> None:
    """T3 — 002-mercadona-scraper-antibaneo: main.py wires MercadonaClient's
    httpx.AsyncClient through build_mercadona_http_client(), not a bare
    httpx.AsyncClient() (spec.md RF-1)."""
    with TestClient(app):
        http_client = app.state.mercadona_client._http_client
        assert http_client.headers["User-Agent"] in USER_AGENTS


def test_lifespan_configures_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """T3 — 003-mercadona-scaper-logging: main.py's lifespan calls
    configure_logging(settings.LOG_LEVEL) (spec.md RF-1)."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    with TestClient(app):
        assert logging.getLogger().level == logging.DEBUG


def test_products_router_requires_api_key() -> None:
    """T5 — 004-mercadona-scraper-authentication: verify_api_key (T2-T4) is
    wired into /api/v1/ via app.include_router's dependencies=, so a
    request without X-API-Key never reaches business logic — proven here
    by mocking MercadonaClient/CacheRepository and asserting they're never
    called (spec.md RF-1). Uses dependency_overrides rather than the real
    lifespan/httpx client so this test never risks a real network call to
    Mercadona if authentication is misconfigured."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client_mock = AsyncMock(spec=MercadonaClient)
    client_mock.search.return_value = []

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client_mock
    app.dependency_overrides[get_settings] = lambda: Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es", REDIS_URL="redis://localhost:6379/0"
    )

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    cache.get.assert_not_called()
    client_mock.search.assert_not_called()


def test_health_returns_ok_without_api_key() -> None:
    """T1 — 005-mercadona-scraper-dockerization: GET /health responds 200
    without requiring X-API-Key and without touching Settings/Redis/
    MercadonaClient — used as the container's liveness probe (spec.md
    RF-9)."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_and_openapi_stay_public_without_api_key() -> None:
    """T8 — 004-mercadona-scraper-authentication: only /api/v1/* requires
    X-API-Key (T5's dependencies= is scoped to that router) — /docs and
    /openapi.json are unaffected (spec.md, duda abierta #2 resuelta)."""
    with TestClient(app) as client:
        docs_response = client.get("/docs")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200


def test_request_logging_middleware_is_registered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T5 — 003-mercadona-scaper-logging: RequestLoggingMiddleware (T4) is
    wired into the real app, so a real request through it leaves start/end
    log lines (spec.md RF-6/RF-7)."""
    with caplog.at_level(logging.INFO):
        with TestClient(app) as client:
            client.get("/docs")

    request_logs = [r for r in caplog.records if r.name == "app.middleware.request_logging"]
    assert len(request_logs) == 2


def test_validation_failure_returns_422_and_logs_start_end(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T11 — 003-mercadona-scaper-logging: a request missing a required
    query param (term) fails validation (422) before reaching get_products,
    but RequestLoggingMiddleware still wraps it (spec.md caso limite,
    RF-6)."""
    with caplog.at_level(logging.INFO):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/products",
                params={"postal_code": "28001"},
                headers={"X-API-Key": TEST_API_KEY},
            )

    assert response.status_code == 422
    request_logs = [r for r in caplog.records if r.name == "app.middleware.request_logging"]
    assert len(request_logs) == 2
    assert request_logs[0].request_id == request_logs[1].request_id
    assert "422" in request_logs[1].getMessage()


def test_unhandled_exception_returns_500_and_logs_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """T6 — 003-mercadona-scaper-logging: an exception product_search.py
    doesn't translate (a real bug, not a Mercadona/Algolia failure) is
    caught by a global exception handler, logged with its traceback, and
    turned into a generic 500 — instead of leaking to uvicorn's own,
    differently-configured logging (spec.md RF-2)."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = RuntimeError("boom")

    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_mercadona_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es", REDIS_URL="redis://localhost:6379/0"
    )

    try:
        with caplog.at_level(logging.ERROR):
            # raise_server_exceptions=False: Starlette's ServerErrorMiddleware
            # calls our handler AND sends its response correctly either way,
            # but by design also re-raises afterwards so a real ASGI server
            # can log it too — TestClient's default re-raises that into the
            # test process itself. We want to inspect the response our
            # handler produced, not have the test client propagate the
            # already-handled exception.
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get(
                    "/api/v1/products",
                    params={"postal_code": "28001", "term": "leche"},
                    headers={"X-API-Key": TEST_API_KEY},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(r.exc_info is not None for r in error_logs)
