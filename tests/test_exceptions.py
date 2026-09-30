"""T2 — 007-mercadona-scraper-warehouse-resolution: PostalCodeNotServedError
is a plain domain exception, sibling of UpstreamUnavailableError (Decision
D4 in plan.md)."""

from app.exceptions import (
    PageOutOfRangeError,
    PostalCodeNotServedError,
    UpstreamUnavailableError,
)


def test_postal_code_not_served_error_is_instantiable() -> None:
    error = PostalCodeNotServedError()

    assert isinstance(error, Exception)


def test_postal_code_not_served_error_accepts_optional_message() -> None:
    error = PostalCodeNotServedError("postal code 99999 has no warehouse")

    assert str(error) == "postal code 99999 has no warehouse"


def test_postal_code_not_served_error_is_not_upstream_unavailable_error() -> None:
    assert not issubclass(PostalCodeNotServedError, UpstreamUnavailableError)


def test_page_out_of_range_error_is_its_own_domain_error() -> None:
    """T8 — 008-mercadona-scraper-search-completeness, RF-9: distinct from
    the other domain errors so the route can map it to its own 404."""
    error = PageOutOfRangeError("page 6 is out of range")

    assert str(error) == "page 6 is out of range"
    assert not issubclass(PageOutOfRangeError, UpstreamUnavailableError)
    assert not issubclass(PageOutOfRangeError, PostalCodeNotServedError)
