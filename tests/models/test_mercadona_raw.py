"""RawAlgoliaProduct / RawAlgoliaSearchResult must validate the real shape of
Mercadona's search backend (Algolia). The hit fixture was captured live
(2026-09-16), not fabricated, so the DTO reflects the real undocumented
shape (constitution #2/#5).

The null-unit-fields and integer-iva cases were first pinned on RawProduct
(the pre-Algolia category-browse model, removed as dead code); they live
here now because RawPriceInstructions is the same model in both shapes.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.mercadona_raw import RawAlgoliaProduct, RawAlgoliaSearchResult
from tests.fixtures.algolia import algolia_response

ALGOLIA_HIT_FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"
)


def _algolia_hit() -> dict[str, object]:
    return json.loads(ALGOLIA_HIT_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_raw_algolia_product_validates_real_sample() -> None:
    product = RawAlgoliaProduct.model_validate(_algolia_hit())

    assert product.id == "10381"
    assert product.display_name == "Leche semidesnatada Hacendado"
    assert product.categories[0].name == "Huevos, leche y mantequilla"


def test_raw_algolia_product_allows_null_price_unit_fields() -> None:
    hit = _algolia_hit()
    hit["price_instructions"]["unit_name"] = None
    hit["price_instructions"]["pack_size"] = None
    hit["price_instructions"]["total_units"] = None

    product = RawAlgoliaProduct.model_validate(hit)

    assert product.price_instructions.unit_name is None
    assert product.price_instructions.pack_size is None
    assert product.price_instructions.total_units is None


def test_raw_algolia_product_allows_integer_iva() -> None:
    """Regression: an early fixture only ever saw iva=null, so the field was
    typed str | None; a real live product had iva=10 (int) and failed
    validation. Sampling a whole real category confirmed iva is always null
    or int, never a string (spec 001, T26 verification notes)."""
    hit = _algolia_hit()
    hit["price_instructions"]["iva"] = 10

    product = RawAlgoliaProduct.model_validate(hit)

    assert product.price_instructions.iva == 10


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
