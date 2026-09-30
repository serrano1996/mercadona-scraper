"""T10 — 008-mercadona-scraper-search-completeness: end-to-end coverage of
real totals, pagination and term normalization through the real app +
lifespan (fakeredis for Redis, respx for all outbound HTTP — zero real
calls to Mercadona). Numbers mirror the live check of 2026-09-30:
"leche" has 233 hits over 5 pages of 50, the last one with 33."""

import json
from pathlib import Path

import httpx
import respx
from httpx import AsyncClient

from tests.fixtures.algolia import algolia_response
from tests.integration.conftest import mock_change_pc

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


def _mock_upstream(respx_mock: respx.MockRouter, algolia_body: dict[str, object]) -> respx.Route:
    mock_change_pc(respx_mock)
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    return respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json=algolia_body)
    )


def _hits(count: int) -> list[dict[str, object]]:
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [hit] * count


def _algolia_params(route: respx.Route) -> list[str]:
    body = json.loads(route.calls.last.request.content)
    return body["requests"][0]["params"].split("&")


async def test_first_page_reports_the_real_total(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """H1, RF-6, RF-7, RF-8: no page/page_size -> first page of 50, and
    total_results is the real 233, not the 50 products in the page."""
    _mock_upstream(respx_mock, algolia_response(_hits(50), nb_hits=233, nb_pages=5))

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["products"]) == 50
    assert body["search"]["total_results"] == 233
    assert body["search"]["total_pages"] == 5
    assert body["search"]["page"] == 1
    assert body["search"]["page_size"] == 50


async def test_last_page_is_requested_as_algolia_page_minus_one(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """H2, RF-5: public page 5 is Algolia page 4."""
    algolia_route = _mock_upstream(respx_mock, algolia_response(_hits(33), nb_hits=233, nb_pages=5))

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche", "page": 5}
    )

    assert response.status_code == 200
    assert len(response.json()["products"]) == 33
    assert response.json()["search"]["page"] == 5
    assert "page=4" in _algolia_params(algolia_route)


async def test_out_of_range_page_is_404_and_never_cached(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-9: Algolia's real out-of-range answer (no hits, nbHits 0,
    nbPages 0) becomes 404, and repeating the request calls Algolia again
    because nothing was cached."""
    algolia_route = _mock_upstream(respx_mock, algolia_response([], nb_hits=0, nb_pages=0))
    params = {"postal_code": "28001", "term": "leche", "page": 6}

    first = await client.get("/api/v1/products", params=params)
    second = await client.get("/api/v1/products", params=params)

    assert first.status_code == 404
    assert first.json() == {"detail": "Page out of range"}
    assert second.status_code == 404
    assert algolia_route.call_count == 2


async def test_equivalent_terms_share_one_cache_entry(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """H4, RF-3, RF-10: "Leche" and "leche " normalize to the same term, so
    the second request is a cache hit and reports the normalized term."""
    algolia_route = _mock_upstream(respx_mock, algolia_response(_hits(1)))

    first = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "Leche"})
    second = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "leche "})

    assert first.status_code == 200
    assert second.status_code == 200
    assert algolia_route.call_count == 1
    assert "query=leche" in _algolia_params(algolia_route)
    assert second.json()["search"]["term"] == "leche"


async def test_blank_term_is_rejected_before_any_upstream_call(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """H3, RF-1: a blank term would return Mercadona's whole catalog; it is
    rejected with 422 and no request leaves the app (no routes are mocked,
    so any outbound call would fail the test)."""
    response = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "  "})

    assert response.status_code == 422
