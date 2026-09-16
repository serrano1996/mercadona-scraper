"""T20 — Integration RF-2: a term with no Algolia hits returns 200 with
an empty products list, not an error."""

import httpx
import respx
from httpx import AsyncClient

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


def _mock_upstream_chain_with_no_hits(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": []}]})
    )


async def test_get_products_returns_empty_list_for_term_with_no_matches(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    _mock_upstream_chain_with_no_hits(respx_mock)

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "xyz-no-existe"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["products"] == []
    assert body["search"]["total_results"] == 0
