"""T19 — Integration RF-1: GET /api/v1/products with a mocked upstream
chain returns 200 and the exact ProductSearchResponse shape."""

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


def _mock_upstream_chain(respx_mock: respx.MockRouter) -> None:
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


async def test_get_products_returns_exact_response_shape(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    _mock_upstream_chain(respx_mock)

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 200
    body = response.json()

    assert body["search"]["postal_code"] == "28001"
    assert body["search"]["term"] == "leche"
    assert body["search"]["warehouse"] == "mad1"
    assert body["search"]["strategy_used"] == "algolia"
    assert body["search"]["total_results"] == 1
    assert set(body["search"].keys()) == {
        "postal_code",
        "term",
        "warehouse",
        "strategy_used",
        "scraped_at",
        "total_results",
    }

    assert len(body["products"]) == 1
    product = body["products"][0]
    assert product == {
        "id": "10381",
        "name": "Leche semidesnatada Hacendado",
        "price": 5.04,
        "price_format": "0.84 €/L",
        "image_url": (
            "https://prod-mercadona.imgix.net/images/"
            "b91d8b8bafd5eabab8961aabbe16c28b.jpg?fit=crop&h=300&w=300"
        ),
        "category": "Huevos, leche y mantequilla",
    }
