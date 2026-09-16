"""T22 — Integration RF-4: a second identical request within the cache TTL
is served from cache, without hitting Mercadona/Algolia again."""

import json
from pathlib import Path

import httpx
import respx
from httpx import AsyncClient

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


async def test_second_identical_request_served_from_cache(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    manifest_route = respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    bundle_route = respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    algolia_route = respx_mock.post(
        f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
    ).mock(return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]}))

    params = {"postal_code": "28001", "term": "leche"}
    first = await client.get("/api/v1/products", params=params)
    second = await client.get("/api/v1/products", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    assert manifest_route.call_count == 1
    assert bundle_route.call_count == 1
    assert algolia_route.call_count == 1
