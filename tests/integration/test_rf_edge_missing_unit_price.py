"""T24 — Integration caso limite: a product with no per-unit price info
(bulk_price missing) returns 200 with price_format: null, not a
validation failure (spec.md caso limite "Aumento de precios / Cambio de
formato")."""

import json
from pathlib import Path

import httpx
import respx
from httpx import AsyncClient

from tests.integration.conftest import mock_change_pc

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


async def test_missing_bulk_price_returns_null_price_format(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    mock_change_pc(respx_mock)
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    hit["price_instructions"]["bulk_price"] = None
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]})
    )

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 200
    product = response.json()["products"][0]
    assert product["price_format"] is None
    assert product["price"] == 5.04
