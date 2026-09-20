"""T23 — Integration caso limite: Redis inaccesible degrada con elegancia.
La respuesta sigue siendo 200 via scraping directo, con un warning
logueado, no un error (spec.md caso limite "Cache inaccesible", Decision
D5 in plan.md). Uses its own broken-Redis client fixture — the shared
`client` fixture in conftest.py is wired to a healthy fakeredis on
purpose, this test needs the opposite."""

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.main import app as fastapi_app
from tests.integration.conftest import TEST_API_KEY

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"

# Synthetic values — never the real production credentials (see the
# incident documented in Decision D7, plan.md).
FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
BUNDLE_JS_WITH_CREDENTIALS = (
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    'REACT_APP_ALGOLIA_NAME:"products_prod"'
)


class _BrokenRedisFactory:
    @staticmethod
    def from_url(*_args: object, **_kwargs: object) -> AsyncMock:
        broken = AsyncMock()
        broken.get.side_effect = RedisConnectionError("connection refused")
        broken.set.side_effect = RedisConnectionError("connection refused")
        return broken


@pytest.fixture
async def client_with_broken_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr("app.main.Redis", _BrokenRedisFactory)

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


async def test_redis_down_degrades_to_direct_scrape(
    client_with_broken_redis: AsyncClient,
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]})
    )

    with caplog.at_level(logging.WARNING):
        response = await client_with_broken_redis.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
        )

    assert response.status_code == 200
    assert len(response.json()["products"]) == 1
    assert any(record.levelno == logging.WARNING for record in caplog.records)
