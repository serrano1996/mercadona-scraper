"""T3 — RawProduct must validate a real Mercadona product payload without errors.

Fixture captured live from https://tienda.mercadona.es/api/categories/72/ (2026-09-16),
category "Leche y bebidas vegetales" — not fabricated, so the DTO reflects the real
undocumented shape (constitution #2/#5).
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.mercadona_raw import RawAlgoliaSearchResult, RawProduct
from tests.fixtures.algolia import algolia_response

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


def test_raw_product_allows_integer_iva() -> None:
    """Regression: T3's fixture only ever saw iva=null, so the field was
    typed str | None. A real live request during T26's manual verification
    hit a product with iva=10 (int) and failed validation — sampled a whole
    real category afterwards and confirmed iva is always null or int, never
    a string (see Decision in plan.md's T26 verification notes)."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["price_instructions"]["iva"] = 10

    product = RawProduct.model_validate(payload)

    assert product.price_instructions.iva == 10


ALGOLIA_HIT_FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"
)


def _algolia_result(**overrides: object) -> dict[str, object]:
    hit = json.loads(ALGOLIA_HIT_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = algolia_response([hit], nb_hits=233, nb_pages=5)["results"][0]
    return {**result, **overrides}


def test_raw_algolia_search_result_keeps_real_totals() -> None:
    """T5 — 008-mercadona-scraper-search-completeness, RF-6/RF-7: the
    real total (nbHits) and page count (nbPages) survive validation, not
    just the hits of the current page."""
    result = RawAlgoliaSearchResult.model_validate(_algolia_result())

    assert result.nbHits == 233
    assert result.nbPages == 5
    assert len(result.hits) == 1
    assert result.hits[0].id == "10381"


@pytest.mark.parametrize("missing_field", ["nbHits", "nbPages"])
def test_raw_algolia_search_result_requires_totals(missing_field: str) -> None:
    """T5 — Decision D3 in plan.md: no default for the totals — if Algolia
    ever stops sending them, fail loudly instead of reporting a fake
    total."""
    payload = _algolia_result()
    del payload[missing_field]

    with pytest.raises(ValidationError):
        RawAlgoliaSearchResult.model_validate(payload)
