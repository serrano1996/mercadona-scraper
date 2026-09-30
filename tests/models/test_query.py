"""T4 — ProductQuery requires both postal_code and term (Decision D4 in plan.md)."""

import pytest
from pydantic import ValidationError

from app.models.query import ProductQuery


def test_product_query_valid_with_both_fields() -> None:
    query = ProductQuery(postal_code="28001", term="leche")

    assert query.postal_code == "28001"
    assert query.term == "leche"


def test_product_query_missing_postal_code_raises() -> None:
    with pytest.raises(ValidationError):
        ProductQuery(term="leche")  # type: ignore[call-arg]


def test_product_query_missing_term_raises() -> None:
    with pytest.raises(ValidationError):
        ProductQuery(postal_code="28001")  # type: ignore[call-arg]


@pytest.mark.parametrize("postal_code", ["28001", "01001", "51001"])
def test_product_query_accepts_valid_5_digit_postal_codes(postal_code: str) -> None:
    """T7 — 007-mercadona-scraper-warehouse-resolution, RF-1. `01001` keeps
    its leading zero (Álava, verified live on 2026-09-24)."""
    query = ProductQuery(postal_code=postal_code, term="leche")

    assert query.postal_code == postal_code


@pytest.mark.parametrize(
    "postal_code",
    [
        "1234",  # too short
        "123456",  # too long
        "abcde",  # letters
        "2800a",  # letter mixed in
        " 28001",  # leading whitespace
        "",  # empty
        "٢٨٠٠١",  # Arabic-indic digits, not [0-9]
    ],
)
def test_product_query_rejects_invalid_postal_codes(postal_code: str) -> None:
    """T7 — RF-1: rejected before any call to Mercadona."""
    with pytest.raises(ValidationError):
        ProductQuery(postal_code=postal_code, term="leche")


@pytest.mark.parametrize(
    ("raw_term", "normalized"),
    [
        ("Leche", "leche"),
        ("  leche  ", "leche"),
        ("leche   entera", "leche entera"),
        ("\tLeche\n", "leche"),
    ],
)
def test_product_query_normalizes_term(raw_term: str, normalized: str) -> None:
    """T1 — 008-mercadona-scraper-search-completeness, RF-3: edge
    whitespace changes Algolia's results ("  leche  " -> 197 hits vs 233,
    verified live 2026-09-30); case and repeated inner spaces don't, so
    normalizing never makes a result worse."""
    query = ProductQuery(postal_code="28001", term=raw_term)

    assert query.term == normalized


@pytest.mark.parametrize("term", ["", "   ", "a" * 101])
def test_product_query_rejects_empty_blank_or_too_long_term(term: str) -> None:
    """T1 — RF-1/RF-2: a blank term returns Mercadona's whole catalog
    (4299 hits, verified live), so it is rejected before any call."""
    with pytest.raises(ValidationError):
        ProductQuery(postal_code="28001", term=term)


@pytest.mark.parametrize("term", ["a" * 100, "  " + "a" * 100 + "   "])
def test_product_query_measures_length_after_normalizing(term: str) -> None:
    """T1 — RF-2: the 100-char limit applies to the normalized term."""
    query = ProductQuery(postal_code="28001", term=term)

    assert query.term == "a" * 100


def test_product_query_pagination_defaults() -> None:
    """T6 — 008-mercadona-scraper-search-completeness, RF-5/RF-8: without
    page/page_size a query asks for the same first page of 50 as before."""
    query = ProductQuery(postal_code="28001", term="leche")

    assert query.page == 1
    assert query.page_size == 50


@pytest.mark.parametrize("page_size", [1, 100])
def test_product_query_accepts_page_size_bounds(page_size: int) -> None:
    query = ProductQuery(postal_code="28001", term="leche", page_size=page_size)

    assert query.page_size == page_size


@pytest.mark.parametrize(
    ("field", "value"), [("page", 0), ("page", -1), ("page_size", 0), ("page_size", 101)]
)
def test_product_query_rejects_out_of_range_pagination(field: str, value: int) -> None:
    """T6 — RF-5: page is 1-based; page_size is capped at 100."""
    with pytest.raises(ValidationError):
        ProductQuery.model_validate({"postal_code": "28001", "term": "leche", field: value})
