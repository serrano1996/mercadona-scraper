"""T1 — 011-mercadona-scraper-upstream-schema-resilience: end-to-end behavior
when Mercadona's Algolia hits change shape. Each case mutates the real
captured hit (tests/fixtures/mercadona_algolia_hit_sample.json) the way the
spec 011 investigation did on 2026-10-01, when every one of these returned
500. Real app + lifespan, fakeredis, respx: nothing leaves the machine.

- A field the API does not use disappears or changes type -> 200 (RF-1).
- A field the API does use is missing -> 502, and nothing is cached (RF-3).
"""

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
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

Mutation = Callable[[dict[str, dict[str, object]]], None]


def _mock_upstream(respx_mock: respx.MockRouter, mutate: Mutation) -> respx.Route:
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    mutate(hit)
    mock_change_pc(respx_mock)
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    return respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json=algolia_response([hit]))
    )


# Strict: documents the target behavior without breaking the suite, and
# fails with XPASS(strict) as soon as a task fixes the case, forcing that
# task to remove the mark (tasks.md 011).
_FAILS_TODAY = pytest.mark.xfail(
    strict=True, reason="spec 011: unvalidated upstream change, 500 today"
)


def _unchanged(hit: dict[str, dict[str, object]]) -> None:
    pass


def _without_popularity_score(hit: dict[str, dict[str, object]]) -> None:
    hit.pop("popularity_score")


def _without_object_id(hit: dict[str, dict[str, object]]) -> None:
    hit.pop("objectID")


def _without_badges_is_water(hit: dict[str, dict[str, object]]) -> None:
    hit["badges"].pop("is_water")


def _selling_method_as_text(hit: dict[str, dict[str, object]]) -> None:
    hit["price_instructions"]["selling_method"] = "kg"


@pytest.mark.parametrize(
    "mutate",
    [
        _unchanged,
        pytest.param(_without_popularity_score, marks=_FAILS_TODAY),
        pytest.param(_without_object_id, marks=_FAILS_TODAY),
        pytest.param(_without_badges_is_water, marks=_FAILS_TODAY),
        pytest.param(_selling_method_as_text, marks=_FAILS_TODAY),
    ],
)
async def test_changes_to_unused_fields_do_not_break_search(
    client: AsyncClient, respx_mock: respx.MockRouter, mutate: Mutation
) -> None:
    """RF-1, H1: the API only depends on the fields it maps."""
    _mock_upstream(respx_mock, mutate)

    response = await client.get(
        "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
    )

    assert response.status_code == 200
    assert response.json()["products"][0]["id"] == "10381"


@_FAILS_TODAY
async def test_missing_used_field_is_502_and_not_cached(
    client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """RF-3, H2: a broken field the API needs is Mercadona's contract
    breaking — 502, never 500 — and the failure is not cached, so the next
    request asks Algolia again."""

    def _without_unit_price(hit: dict[str, dict[str, object]]) -> None:
        hit["price_instructions"].pop("unit_price")

    algolia_route = _mock_upstream(respx_mock, _without_unit_price)
    params = {"postal_code": "28001", "term": "leche"}

    first = await client.get("/api/v1/products", params=params)
    second = await client.get("/api/v1/products", params=params)

    assert first.status_code == 502
    assert second.status_code == 502
    assert algolia_route.call_count == 2
