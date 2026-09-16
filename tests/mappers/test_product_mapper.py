"""T6 — product_mapper maps RawProduct -> ProductOut; missing per-unit price
info degrades price_format to None instead of failing validation
(spec.md caso limite "Aumento de precios / Cambio de formato")."""

import json
from pathlib import Path

from app.mappers.product_mapper import map_raw_product_to_product_out
from app.models.mercadona_raw import RawProduct

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_product_sample.json"


def _load_raw_product(**price_instructions_overrides: str | None) -> RawProduct:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["price_instructions"].update(price_instructions_overrides)
    return RawProduct.model_validate(payload)


def test_maps_id_name_price_image_category() -> None:
    raw = _load_raw_product()

    product = map_raw_product_to_product_out(raw)

    assert product.id == "10531"
    assert product.name == "Leche semidesnatada Asturiana"
    assert product.price == 6.54
    assert product.image_url == raw.thumbnail
    assert product.category == "Huevos, leche y mantequilla"


def test_price_format_built_from_bulk_price_and_reference_format() -> None:
    raw = _load_raw_product()

    product = map_raw_product_to_product_out(raw)

    assert product.price_format == "1.09 €/L"


def test_price_format_is_none_when_bulk_price_missing() -> None:
    raw = _load_raw_product(bulk_price=None)

    product = map_raw_product_to_product_out(raw)

    assert product.price_format is None


def test_price_format_is_none_when_reference_format_missing() -> None:
    raw = _load_raw_product(reference_format=None)

    product = map_raw_product_to_product_out(raw)

    assert product.price_format is None
