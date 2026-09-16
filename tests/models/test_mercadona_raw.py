"""T3 — RawProduct must validate a real Mercadona product payload without errors.

Fixture captured live from https://tienda.mercadona.es/api/categories/72/ (2026-09-16),
category "Leche y bebidas vegetales" — not fabricated, so the DTO reflects the real
undocumented shape (constitution #2/#5).
"""

import json
from pathlib import Path

from app.models.mercadona_raw import RawProduct

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_product_sample.json"


def test_raw_product_validates_real_mercadona_sample() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    product = RawProduct.model_validate(payload)

    assert product.id == "10531"
    assert product.display_name == "Leche semidesnatada Asturiana"
    assert product.packaging == "Pack-6"
    assert product.status is None
    assert product.price_instructions.unit_price == "6.54"
    assert product.price_instructions.bulk_price == "1.09"
    assert product.price_instructions.previous_unit_price == "        7.02"
    assert product.categories[0].name == "Huevos, leche y mantequilla"


def test_raw_product_allows_null_price_unit_fields() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["price_instructions"]["unit_name"] = None
    payload["price_instructions"]["pack_size"] = None
    payload["price_instructions"]["total_units"] = None

    product = RawProduct.model_validate(payload)

    assert product.price_instructions.unit_name is None
    assert product.price_instructions.pack_size is None
    assert product.price_instructions.total_units is None
