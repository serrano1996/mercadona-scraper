"""T2 — 007-mercadona-scraper-warehouse-resolution: PostalCodeNotServedError
is a plain domain exception, sibling of UpstreamUnavailableError (Decision
D4 in plan.md)."""

from app.exceptions import PostalCodeNotServedError, UpstreamUnavailableError


def test_postal_code_not_served_error_is_instantiable() -> None:
    error = PostalCodeNotServedError()

    assert isinstance(error, Exception)


def test_postal_code_not_served_error_accepts_optional_message() -> None:
    error = PostalCodeNotServedError("postal code 99999 has no warehouse")

    assert str(error) == "postal code 99999 has no warehouse"


def test_postal_code_not_served_error_is_not_upstream_unavailable_error() -> None:
    assert not issubclass(PostalCodeNotServedError, UpstreamUnavailableError)
