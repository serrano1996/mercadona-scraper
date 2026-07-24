import logging

from formatters import ProductFormatter
from models import ProductResult


# --------------------------------------------------------------------- #
# map_product — price mapping
# --------------------------------------------------------------------- #


def test_map_product_full_price_instructions():
    p = {
        "id": 123,
        "display_name": "Leche entera",
        "thumbnail": "https://example.com/leche.jpg",
        "price_instructions": {
            "unit_price": "1.99",
            "bulk_price": "1.50",
            "reference_price": "1.99",
            "reference_format": "kg",
        },
        "categories": [{"name": "Lácteos"}],
    }

    result = ProductFormatter.map_product(p)

    assert isinstance(result, ProductResult)
    assert result.id == "123"
    assert result.name == "Leche entera"
    assert result.price == 1.99
    assert result.price_format == "1.99 €/kg"
    assert result.image_url == "https://example.com/leche.jpg"
    assert result.category == "Lácteos"


def test_map_product_missing_price_instructions_defaults_to_zero_and_warns(caplog):
    p = {"id": 1, "display_name": "Producto sin precio"}

    with caplog.at_level(logging.WARNING):
        result = ProductFormatter.map_product(p)

    assert result.price == 0.0
    assert any("sin 'price_instructions'" in rec.message for rec in caplog.records)


def test_map_product_empty_price_instructions_dict_defaults_to_zero_and_warns(caplog):
    p = {"id": 1, "display_name": "Producto", "price_instructions": {}}

    with caplog.at_level(logging.WARNING):
        result = ProductFormatter.map_product(p)

    assert result.price == 0.0
    assert any("sin 'price_instructions'" in rec.message for rec in caplog.records)


def test_map_product_reference_format_empty_omits_slash_suffix():
    p = {
        "id": 1,
        "display_name": "Producto",
        "price_instructions": {
            "unit_price": "2.50",
            "reference_price": "2.50",
            "reference_format": "",
        },
    }

    result = ProductFormatter.map_product(p)

    assert result.price == 2.50
    assert result.price_format == "2.50 €"
    assert "/" not in result.price_format


def test_map_product_uses_bulk_price_when_unit_price_missing():
    p = {
        "id": 1,
        "display_name": "Producto a granel",
        "price_instructions": {"bulk_price": "3.20"},
    }

    result = ProductFormatter.map_product(p)

    assert result.price == 3.20


# --------------------------------------------------------------------- #
# map_product — category resolution
# --------------------------------------------------------------------- #


def test_map_product_category_name_takes_priority_over_categories_list():
    p = {
        "id": 1,
        "display_name": "Producto",
        "_category_name": "Categoría inyectada",
        "categories": [{"name": "Categoría original"}],
    }

    result = ProductFormatter.map_product(p)

    assert result.category == "Categoría inyectada"


def test_map_product_falls_back_to_first_category_when_no_injected_name():
    p = {
        "id": 1,
        "display_name": "Producto",
        "categories": [{"name": "Categoría original"}, {"name": "Otra"}],
    }

    result = ProductFormatter.map_product(p)

    assert result.category == "Categoría original"


def test_map_product_empty_categories_yields_empty_category_string():
    p = {"id": 1, "display_name": "Producto", "categories": []}

    result = ProductFormatter.map_product(p)

    assert result.category == ""


def test_map_product_no_categories_key_yields_empty_category_string():
    p = {"id": 1, "display_name": "Producto"}

    result = ProductFormatter.map_product(p)

    assert result.category == ""


# --------------------------------------------------------------------- #
# format_output
# --------------------------------------------------------------------- #


def test_format_output_wraps_products_into_scraper_result():
    raw_products = [
        {
            "id": 1,
            "display_name": "Leche entera",
            "price_instructions": {"unit_price": "1.05"},
            "categories": [{"name": "Lácteos"}],
        },
        {
            "id": 2,
            "display_name": "Leche desnatada",
            "price_instructions": {"unit_price": "0.95"},
            "categories": [{"name": "Lácteos"}],
        },
    ]

    result = ProductFormatter.format_output(
        raw_products,
        warehouse="mad1",
        postal_code="28001",
        term="leche",
        strategy_used="api",
    )

    assert result.search.postal_code == "28001"
    assert result.search.term == "leche"
    assert result.search.warehouse == "mad1"
    assert result.search.strategy_used == "api"
    assert result.search.total_results == 2
    assert result.search.scraped_at.endswith("Z")
    assert len(result.products) == 2
    assert result.products[0].name == "Leche entera"
    assert result.products[1].name == "Leche desnatada"


def test_format_output_with_no_products_has_zero_total_results():
    result = ProductFormatter.format_output(
        [], warehouse="mad1", postal_code="28001", term="inexistente"
    )

    assert result.search.total_results == 0
    assert result.products == []
    assert result.search.strategy_used == "api"  # default value
