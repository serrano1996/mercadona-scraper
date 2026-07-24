from exceptions import (
    APISchemaError,
    MercadonaScraperError,
    SearchFailedError,
    WarehouseError,
)


def test_mercadona_scraper_error_is_exception_subclass():
    assert issubclass(MercadonaScraperError, Exception)


def test_warehouse_error_is_mercadona_scraper_error_subclass():
    assert issubclass(WarehouseError, MercadonaScraperError)


def test_api_schema_error_is_mercadona_scraper_error_subclass():
    assert issubclass(APISchemaError, MercadonaScraperError)


def test_search_failed_error_is_mercadona_scraper_error_subclass():
    assert issubclass(SearchFailedError, MercadonaScraperError)


def test_exceptions_are_raisable_and_catchable_as_base():
    for exc_cls in (WarehouseError, APISchemaError, SearchFailedError):
        try:
            raise exc_cls("boom")
        except MercadonaScraperError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError(f"{exc_cls} was not caught as MercadonaScraperError")
