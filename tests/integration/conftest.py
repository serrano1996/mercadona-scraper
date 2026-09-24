"""T18 — shared fixtures for RF integration tests (T19-T24): the real
FastAPI app running through its real lifespan (app.main.app), with Redis
swapped for fakeredis so no real Redis is needed. Mercadona/Algolia HTTP
calls are intercepted with respx — use the `respx_mock` fixture the respx
pytest plugin provides automatically (no custom fixture needed for it),
registering routes per test as done in tests/scrapers/test_mercadona_client*.py.
"""

from collections.abc import AsyncIterator

import fakeredis
import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app

# T6 — 004-mercadona-scraper-authentication: shared valid token so every
# integration test authenticates by default (the `client` fixture sends it
# on every request) without each test having to know about auth.
TEST_API_KEY = "integration-test-api-key"

# T11 — 007-mercadona-scraper-warehouse-resolution: every request now
# resolves postal_code -> warehouse via change-pc before reaching
# Mercadona's search backend. Tests written for specs 001-006 predate
# this and don't mock it — mock_change_pc gives them a one-line, non-
# autouse way to keep resolving to "mad1" (their original hardcoded
# default) without changing what each test is actually asserting.
CHANGE_PC_URL = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"


def mock_change_pc(respx_mock: respx.MockRouter, warehouse: str = "mad1") -> respx.Route:
    return respx_mock.put(CHANGE_PC_URL).mock(
        return_value=httpx.Response(200, headers={"x-customer-wh": warehouse})
    )


@pytest.fixture(autouse=True)
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCADONA_BASE_URL", "https://tienda.mercadona.es")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("API_KEYS", TEST_API_KEY)


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
        AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-API-Key": TEST_API_KEY},
        ) as http_client,
    ):
        yield http_client
