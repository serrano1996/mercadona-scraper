"""T5 — public API schemas: ProductOut, SearchMeta, ProductSearchResponse."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.product import ProductOut, ProductSearchResponse, SearchMeta


def test_product_out_allows_null_price_format() -> None:
    product = ProductOut(
        id="1",
        name="Leche entera",
        price=1.05,
        price_format=None,
        image_url="https://example.com/1.jpg",
        category="Lácteos",
    )

    assert product.price_format is None


def test_product_out_accepts_price_format_value() -> None:
    product = ProductOut(
        id="1",
        name="Leche entera",
        price=1.05,
        price_format="1.05 €/L",
        image_url="https://example.com/1.jpg",
        category="Lácteos",
    )

    assert product.price_format == "1.05 €/L"


def test_search_meta_valid() -> None:
    meta = SearchMeta(
        postal_code="28001",
        term="leche",
        warehouse="mad1",
        strategy_used="api",
        scraped_at=datetime.now(UTC),
        total_results=1,
    )

    assert meta.total_results == 1


def test_product_search_response_allows_empty_products_list() -> None:
    meta = SearchMeta(
        postal_code="28001",
        term="xyz-no-existe",
        warehouse="mad1",
        strategy_used="api",
        scraped_at=datetime.now(UTC),
        total_results=0,
    )

    response = ProductSearchResponse(search=meta, products=[])

    assert response.products == []


def test_product_search_response_missing_search_raises() -> None:
    with pytest.raises(ValidationError):
        ProductSearchResponse(products=[])  # type: ignore[call-arg]
