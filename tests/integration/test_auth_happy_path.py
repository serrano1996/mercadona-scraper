"""T9 — 004-mercadona-scraper-authentication: a valid X-API-Key doesn't
alter the happy path — same exact response shape as T19 (spec 001), now
passing through authentication (D1 in plan.md doesn't change behavior for
an authenticated client, spec.md RF-1 regression check)."""

from httpx import AsyncClient
from respx import MockRouter

from tests.integration.conftest import TEST_API_KEY
from tests.integration.test_rf1_happy_path import _mock_upstream_chain


async def test_get_products_returns_exact_response_shape_with_valid_api_key(
    client: AsyncClient, respx_mock: MockRouter
) -> None:
    _mock_upstream_chain(respx_mock)

    response = await client.get(
        "/api/v1/products",
        params={"postal_code": "28001", "term": "leche"},
        headers={"X-API-Key": TEST_API_KEY},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["search"]["postal_code"] == "28001"
    assert body["search"]["term"] == "leche"
    assert body["search"]["warehouse"] == "mad1"
    assert body["search"]["strategy_used"] == "algolia"
    assert body["search"]["total_results"] == 1

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
