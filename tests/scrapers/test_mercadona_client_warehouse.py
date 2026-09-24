"""T2 — 007-mercadona-scraper-warehouse-resolution: WarehouseHeaderMissing
is a plain domain exception, sibling of AlgoliaCredentialsUnavailable
(Decision D4 in plan.md). resolve_warehouse itself is built in T3/T4."""

from app.scrapers.mercadona_client import AlgoliaCredentialsUnavailable, WarehouseHeaderMissing


def test_warehouse_header_missing_is_instantiable() -> None:
    error = WarehouseHeaderMissing()

    assert isinstance(error, Exception)


def test_warehouse_header_missing_accepts_optional_message() -> None:
    error = WarehouseHeaderMissing("Mercadona returned 200 without x-customer-wh")

    assert str(error) == "Mercadona returned 200 without x-customer-wh"


def test_warehouse_header_missing_is_not_algolia_credentials_unavailable() -> None:
    assert not issubclass(WarehouseHeaderMissing, AlgoliaCredentialsUnavailable)
