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
