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
