"""T12 (mapper prerequisite) — product_mapper maps RawAlgoliaProduct ->
ProductOut, same price_format nullability rule as T6's
map_raw_product_to_product_out (spec.md caso limite "sin precio por unidad")."""

import json
from pathlib import Path

from app.mappers.product_mapper import map_raw_algolia_product_to_product_out
from app.models.mercadona_raw import RawAlgoliaProduct

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"


def _load_raw_algolia_product(**price_instructions_overrides: str | None) -> RawAlgoliaProduct:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["price_instructions"].update(price_instructions_overrides)
    return RawAlgoliaProduct.model_validate(payload)


def test_maps_id_name_price_image_category() -> None:
    raw = _load_raw_algolia_product()

    product = map_raw_algolia_product_to_product_out(raw)

    assert product.id == "10381"
    assert product.name == "Leche semidesnatada Hacendado"
    assert product.price == 5.04
    assert product.image_url == raw.thumbnail
    assert product.category == "Huevos, leche y mantequilla"


def test_price_format_built_from_bulk_price_and_reference_format() -> None:
    raw = _load_raw_algolia_product()

    product = map_raw_algolia_product_to_product_out(raw)

    assert product.price_format == "0.84 €/L"


def test_price_format_is_none_when_bulk_price_missing() -> None:
    raw = _load_raw_algolia_product(bulk_price=None)

    product = map_raw_algolia_product_to_product_out(raw)

    assert product.price_format is None


def test_price_format_is_none_when_reference_format_missing() -> None:
    raw = _load_raw_algolia_product(reference_format=None)

    product = map_raw_algolia_product_to_product_out(raw)

    assert product.price_format is None
