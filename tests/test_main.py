"""T17 — main.py assembles FastAPI, mounts the products router, and its
lifespan wires httpx/redis clients into app.state for the route
dependencies (app/api/v1/products.py) to read."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scrapers.http_client_factory import USER_AGENTS


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
