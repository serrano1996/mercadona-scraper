"""T18 — shared fixtures for RF integration tests (T19-T24): the real
FastAPI app running through its real lifespan (app.main.app), with Redis
swapped for fakeredis so no real Redis is needed. Mercadona/Algolia HTTP
calls are intercepted with respx — use the `respx_mock` fixture the respx
pytest plugin provides automatically (no custom fixture needed for it),
registering routes per test as done in tests/scrapers/test_mercadona_client*.py.
"""

from collections.abc import AsyncIterator

import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app


@pytest.fixture(autouse=True)
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCADONA_BASE_URL", "https://tienda.mercadona.es")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


class _FreshFakeRedisFactory:
    """`fakeredis.FakeAsyncRedis.from_url(url)` shares in-memory state across
    instances built from the *same* url (it mirrors real Redis: same
    connection string = same server) — that leaked cache entries between
    tests here. Ignoring the url and building a bare FakeAsyncRedis() per
    call keeps each test's cache isolated."""

    @staticmethod
    def from_url(*_args: object, **_kwargs: object) -> fakeredis.FakeAsyncRedis:
        return fakeredis.FakeAsyncRedis()


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr("app.main.Redis", _FreshFakeRedisFactory)

    transport = ASGITransport(app=fastapi_app)
    async with (
        fastapi_app.router.lifespan_context(fastapi_app),
        AsyncClient(transport=transport, base_url="http://test") as http_client,
    ):
        yield http_client
