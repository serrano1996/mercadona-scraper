"""T2/T3 — 007-mercadona-scraper-warehouse-resolution: WarehouseHeaderMissing
is a plain domain exception, sibling of AlgoliaCredentialsUnavailable
(Decision D4 in plan.md). T3 covers MercadonaClient.resolve_warehouse's
happy path against Mercadona's real change-pc endpoint (verified live
2026-09-24, see spec.md). T4 adds its error cases."""

import httpx
import respx

from app.core.config import Settings
from app.scrapers.mercadona_client import (
    AlgoliaCredentialsUnavailable,
    MercadonaClient,
    WarehouseHeaderMissing,
)


def test_warehouse_header_missing_is_instantiable() -> None:
    error = WarehouseHeaderMissing()

    assert isinstance(error, Exception)


def test_warehouse_header_missing_accepts_optional_message() -> None:
    error = WarehouseHeaderMissing("Mercadona returned 200 without x-customer-wh")

    assert str(error) == "Mercadona returned 200 without x-customer-wh"


def test_warehouse_header_missing_is_not_algolia_credentials_unavailable() -> None:
    assert not issubclass(WarehouseHeaderMissing, AlgoliaCredentialsUnavailable)


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


async def test_resolve_warehouse_returns_header_value_on_success() -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.put("https://tienda.mercadona.es/api/postal-codes/actions/change-pc/").mock(
            return_value=httpx.Response(
                200, headers={"x-customer-wh": "mad3", "x-customer-pc": "28001"}
            )
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("28001")

    assert warehouse == "mad3"
    assert route.calls.last.request.method == "PUT"
    assert route.calls.last.request.content == b'{"new_postal_code":"28001"}'


async def test_resolve_warehouse_returns_opaque_ids_unchanged() -> None:
    """Ids like `4701` (Canarias) or `3842` (Baleares) are opaque Mercadona
    identifiers, not necessarily 4-letter codes — no format is assumed
    (spec.md, Caso límite)."""
    with respx.mock(assert_all_called=True) as mock:
        mock.put("https://tienda.mercadona.es/api/postal-codes/actions/change-pc/").mock(
            return_value=httpx.Response(200, headers={"x-customer-wh": "4701"})
        )
        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, _settings())
            warehouse = await client.resolve_warehouse("35001")

    assert warehouse == "4701"
