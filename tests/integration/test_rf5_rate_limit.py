"""T10 (spec 002) — Integration: a 429 with a short Retry-After is absorbed
by MercadonaClient's retry, so GET /api/v1/products still responds 200
(002-mercadona-scraper-antibaneo RF-2/RF-3/RF-5)."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from httpx import AsyncClient

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"
MANIFEST_PAYLOAD = {"main.js": "/v815/static/js/main.35c4c08c.chunk.js"}

# Synthetic values — never the real production credentials (see the
# incident documented in Decision D7, plan.md 001).
FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
BUNDLE_JS_WITH_CREDENTIALS = (
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    'REACT_APP_ALGOLIA_NAME:"products_prod"'
)


@pytest.fixture(autouse=True)
def fast_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRY_BASE_DELAY", "0.0")
    monkeypatch.setenv("RETRY_JITTER_MAX_S", "0.0")


async def test_429_with_short_retry_after_is_absorbed(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    manifest_route = respx_mock.get(MANIFEST_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=MANIFEST_PAYLOAD),
        ]
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]})
    )

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 200
    assert manifest_route.call_count == 2
    assert len(response.json()["products"]) == 1


async def test_persistent_429_returns_502(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """T11 (spec 002) — same pattern as spec 001's persistent-5xx test
    (T21), but with 429: the API consumer never needs to know Mercadona/
    Algolia rate-limited us specifically (RF-6)."""
    manifest_route = respx_mock.get(MANIFEST_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(429, headers={"Retry-After": "0"}),
        ]
    )

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 502
    assert manifest_route.call_count == 3
