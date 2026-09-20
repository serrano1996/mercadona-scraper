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


@pytest.fixture(autouse=True)
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCADONA_BASE_URL", "https://tienda.mercadona.es")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


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
                    "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any(r.exc_info is not None for r in error_logs)
