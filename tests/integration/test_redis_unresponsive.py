"""T6 — 010-mercadona-scraper-operational-robustness: end-to-end proof that a
Redis which accepts connections but never answers no longer hangs requests.

Unlike the rest of tests/integration/, this uses the *real* redis-py client
(no fakeredis swap), pointed at a local TCP server that accepts and then
stays silent — the failure mode of a remote Redis (e.g. Upstash) behind a
degraded network. Only a real client proves that the app configures its
timeouts (Decision D4 in plan.md); fakeredis and AsyncMock doubles always
fail instantly. Mercadona/Algolia are mocked with respx as usual: nothing
leaves the machine.

Every request is wrapped in asyncio.wait_for, so a regression (timeouts
removed) fails the test with TimeoutError instead of hanging the suite.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app
from tests.fixtures.algolia import algolia_response
from tests.integration.conftest import TEST_API_KEY, mock_change_pc

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"

# Synthetic values — never the real production credentials (see the
# incident documented in Decision D7, plan.md 001).
FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
BUNDLE_JS_WITH_CREDENTIALS = (
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    'REACT_APP_ALGOLIA_NAME:"products_prod"'
)

REDIS_TIMEOUT_SECONDS = 0.2
# A search does up to four cache operations (warehouse get/set, search
# get/set), each bounded by REDIS_TIMEOUT_SECONDS, plus overhead. Generous
# so a slow CI runner doesn't flake; a hang would blow straight past it.
REQUEST_DEADLINE_SECONDS = 3.0


@pytest.fixture
async def silent_redis_url() -> AsyncIterator[str]:
    """A TCP server that accepts connections and never sends a byte."""
    writers: list[asyncio.StreamWriter] = []

    async def accept_and_stay_silent(
        _reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writers.append(writer)

    server = await asyncio.start_server(accept_and_stay_silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        for writer in writers:
            writer.close()
        server.close()
        await server.wait_closed()


@pytest.fixture
async def client_with_silent_redis(
    silent_redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("REDIS_URL", silent_redis_url)
    monkeypatch.setenv("REDIS_TIMEOUT_SECONDS", str(REDIS_TIMEOUT_SECONDS))

    transport = ASGITransport(app=fastapi_app)
    async with (
        fastapi_app.router.lifespan_context(fastapi_app),
        AsyncClient(
            transport=transport, base_url="http://test", headers={"X-API-Key": TEST_API_KEY}
        ) as http_client,
    ):
        yield http_client


def _mock_upstream(respx_mock: respx.MockRouter) -> None:
    mock_change_pc(respx_mock)
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json=algolia_response([hit]))
    )


async def test_search_completes_without_cache_when_redis_never_answers(
    client_with_silent_redis: AsyncClient,
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RF-2, RF-3, H1: the search degrades to "no cache" (the spec 001/007
    behavior) instead of hanging, and finishes in bounded time."""
    _mock_upstream(respx_mock)

    start = time.monotonic()
    with caplog.at_level(logging.WARNING):
        response = await asyncio.wait_for(
            client_with_silent_redis.get(
                "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
            ),
            timeout=REQUEST_DEADLINE_SECONDS,
        )
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert len(response.json()["products"]) == 1
    assert elapsed < REQUEST_DEADLINE_SECONDS
    assert any("Redis unavailable" in r.getMessage() for r in caplog.records)


async def test_ready_is_503_and_health_is_200_when_redis_never_answers(
    client_with_silent_redis: AsyncClient,
) -> None:
    """RF-7, RF-8, H3: readiness reports the dependency, liveness doesn't."""
    ready = await asyncio.wait_for(
        client_with_silent_redis.get("/ready"), timeout=REQUEST_DEADLINE_SECONDS
    )
    health = await asyncio.wait_for(
        client_with_silent_redis.get("/health"), timeout=REQUEST_DEADLINE_SECONDS
    )

    assert ready.status_code == 503
    assert ready.json() == {"status": "unavailable", "redis": "unreachable"}
    assert health.status_code == 200
