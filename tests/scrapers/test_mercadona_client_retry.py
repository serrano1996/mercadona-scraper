"""T10 — MercadonaClient retries on 5xx/connection errors (Decision D1/D2 in
plan.md), up to RETRY_MAX_ATTEMPTS, with no retry on 4xx."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.core.config import Settings
from app.scrapers.mercadona_client import MercadonaClient

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"
MANIFEST_PAYLOAD = {"main.js": "/v815/static/js/main.35c4c08c.chunk.js"}

# Synthetic values — never commit real Mercadona/Algolia credentials (see
# Decision D7 in plan.md, and the incident it documents).
FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
BUNDLE_JS_WITH_CREDENTIALS = (
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    'REACT_APP_ALGOLIA_NAME:"products_prod"'
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        RETRY_MAX_ATTEMPTS=3,
        RETRY_BASE_DELAY=0.0,
    )


def _algolia_response_with_one_hit() -> dict:
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {"results": [{"hits": [hit]}]}


async def test_retries_up_to_max_attempts_then_raises_on_persistent_5xx(
    settings: Settings,
) -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(MANIFEST_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)]
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with pytest.raises(httpx.HTTPStatusError):
                await client.search(term="leche", warehouse="mad1")

    assert route.call_count == 3


async def test_recovers_on_third_attempt_after_two_5xx(settings: Settings) -> None:
    with respx.mock(assert_all_called=True) as mock:
        manifest_route = mock.get(MANIFEST_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json=MANIFEST_PAYLOAD),
            ]
        )
        mock.get(BUNDLE_URL).mock(return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS))
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(200, json=_algolia_response_with_one_hit())
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            products = await client.search(term="leche", warehouse="mad1")

    assert manifest_route.call_count == 3
    assert len(products) == 1


async def test_does_not_retry_on_4xx(settings: Settings) -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(MANIFEST_URL).mock(return_value=httpx.Response(404))

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with pytest.raises(httpx.HTTPStatusError):
                await client.search(term="leche", warehouse="mad1")

    assert route.call_count == 1
