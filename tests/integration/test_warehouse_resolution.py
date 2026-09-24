"""T12 — 007-mercadona-scraper-warehouse-resolution: end-to-end coverage
of postal_code -> warehouse resolution through the real app + lifespan
(fakeredis swapped in for Redis, respx for all outbound HTTP — zero real
calls to Mercadona). Exercises RF-4, RF-6, RF-7, RF-8, RF-10, RF-11 and
historias H1/H4 together, the way a real deployment would combine them."""

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from httpx import AsyncClient

from tests.integration.conftest import CHANGE_PC_URL
from tests.integration.test_rf_edge_redis_down import client_with_broken_redis  # noqa: F401

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


def _mock_credentials_and_algolia(respx_mock: respx.MockRouter) -> respx.Route:
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]})
    )


def _mock_change_pc_for(respx_mock: respx.MockRouter, postal_code: str, warehouse: str) -> None:
    respx_mock.put(CHANGE_PC_URL, json={"new_postal_code": postal_code}).mock(
        return_value=httpx.Response(200, headers={"x-customer-wh": warehouse})
    )


async def test_different_postal_codes_resolve_to_their_real_warehouse(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-5, RF-6, H1: two postal codes resolving to different warehouses
    get different SearchMeta.warehouse values, and Algolia sees a
    different index per warehouse — not the old hardcoded "mad1"."""
    _mock_change_pc_for(respx_mock, "28001", "mad3")
    _mock_change_pc_for(respx_mock, "46001", "vlc1")
    algolia_route = _mock_credentials_and_algolia(respx_mock)

    madrid = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "leche"})
    valencia = await client.get(
        "/api/v1/products", params={"postal_code": "46001", "term": "leche"}
    )

    assert madrid.status_code == 200
    assert valencia.status_code == 200
    assert madrid.json()["search"]["warehouse"] == "mad3"
    assert valencia.json()["search"]["warehouse"] == "vlc1"

    index_names = [
        json.loads(call.request.content)["requests"][0]["indexName"] for call in algolia_route.calls
    ]
    assert index_names == ["products_prod_mad3_es", "products_prod_vlc1_es"]


async def test_postal_codes_sharing_a_warehouse_share_the_product_cache(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """H4, RF-6: two different postal codes resolving to the SAME
    warehouse hit Algolia only once for the same term. RF-7: each
    response still reflects its own postal_code, not whichever request
    wrote the cache first."""
    _mock_change_pc_for(respx_mock, "28001", "mad3")
    _mock_change_pc_for(respx_mock, "28002", "mad3")
    algolia_route = _mock_credentials_and_algolia(respx_mock)

    first = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "leche"})
    second = await client.get("/api/v1/products", params={"postal_code": "28002", "term": "leche"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert algolia_route.call_count == 1
    assert first.json()["search"]["postal_code"] == "28001"
    assert second.json()["search"]["postal_code"] == "28002"
    assert first.json()["search"]["warehouse"] == "mad3"
    assert second.json()["search"]["warehouse"] == "mad3"


async def test_repeating_the_same_postal_code_reuses_the_cached_warehouse(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-4: a second request for the same postal_code within the TTL
    does not repeat change-pc."""
    change_pc_route = respx_mock.put(CHANGE_PC_URL).mock(
        return_value=httpx.Response(200, headers={"x-customer-wh": "mad3"})
    )
    _mock_credentials_and_algolia(respx_mock)
    params = {"postal_code": "28001", "term": "leche"}

    first = await client.get("/api/v1/products", params=params)
    second = await client.get("/api/v1/products", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert change_pc_route.call_count == 1


async def test_postal_code_without_service_returns_404_and_caches_the_negative_result(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-9, RF-11: a postal_code Mercadona doesn't serve returns 404 both
    times, and the second request doesn't repeat change-pc either — the
    "not served" result is cached too."""
    change_pc_route = respx_mock.put(CHANGE_PC_URL).mock(
        return_value=httpx.Response(
            404, json={"error_msg": "This zip code is outside of our working area"}
        )
    )
    params = {"postal_code": "99999", "term": "leche"}

    first = await client.get("/api/v1/products", params=params)
    second = await client.get("/api/v1/products", params=params)

    assert first.status_code == 404
    assert second.status_code == 404
    assert change_pc_route.call_count == 1


async def test_persistent_change_pc_failure_returns_502(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-8: change-pc failing with 5xx after exhausting retries surfaces
    as 502, the same contract as a search-side upstream failure."""
    change_pc_route = respx_mock.put(CHANGE_PC_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(503)]
    )

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 502
    assert change_pc_route.call_count == 3


async def test_change_pc_response_without_header_returns_502_and_caches_nothing(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-10: a 2xx without x-customer-wh (not observed live, a broken
    upstream contract) maps to 502 — and nothing is cached, so a second
    request calls change-pc again instead of repeating a wrong "not
    served" verdict."""
    change_pc_route = respx_mock.put(CHANGE_PC_URL).mock(return_value=httpx.Response(200))

    first = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "leche"})
    second = await client.get("/api/v1/products", params={"postal_code": "28001", "term": "leche"})

    assert first.status_code == 502
    assert second.status_code == 502
    assert change_pc_route.call_count == 2


async def test_redis_down_still_resolves_warehouse_by_calling_change_pc_every_time(
    client_with_broken_redis: AsyncClient,  # noqa: F811
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Caso límite (spec.md, plan.md D6): if Redis is unreachable,
    warehouse resolution degrades to calling change-pc on every request
    instead of failing the whole search — same policy as the product
    cache (spec 001)."""
    change_pc_route = respx_mock.put(CHANGE_PC_URL).mock(
        return_value=httpx.Response(200, headers={"x-customer-wh": "mad3"})
    )
    _mock_credentials_and_algolia(respx_mock)
    params = {"postal_code": "28001", "term": "leche"}

    with caplog.at_level(logging.WARNING):
        first = await client_with_broken_redis.get("/api/v1/products", params=params)
        second = await client_with_broken_redis.get("/api/v1/products", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert change_pc_route.call_count == 2
