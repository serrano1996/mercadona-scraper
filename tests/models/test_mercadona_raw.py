"""RawAlgoliaProduct / RawAlgoliaSearchResult must validate the real shape of
Mercadona's search backend (Algolia). The hit fixture was captured live
(2026-09-16), not fabricated (constitution #2/#5).

Spec 011: the models declare only the fields the API maps, so a change in
any other field — verified to break every search before — no longer
matters. The fixture still documents the full upstream shape.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.mercadona_raw import (
    RawAlgoliaProduct,
    RawAlgoliaResponse,
    RawAlgoliaSearchResult,
)
from tests.fixtures.algolia import algolia_response

ALGOLIA_HIT_FIXTURE_PATH = (
    Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"
)


def _algolia_hit() -> dict[str, dict[str, object]]:
    return json.loads(ALGOLIA_HIT_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_raw_algolia_product_validates_real_sample() -> None:
    product = RawAlgoliaProduct.model_validate(_algolia_hit())

    assert product.id == "10381"
    assert product.display_name == "Leche semidesnatada Hacendado"
    assert product.categories[0].name == "Huevos, leche y mantequilla"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda hit: hit.pop("popularity_score"),
        lambda hit: hit.pop("objectID"),
        lambda hit: hit.pop("badges"),
        lambda hit: hit["price_instructions"].update(selling_method="kg"),
        lambda hit: hit["price_instructions"].update(iva="not-an-int"),
        lambda hit: hit.update(brand_new_upstream_field={"x": 1}),
    ],
    ids=[
        "no-popularity_score",
        "no-objectID",
        "no-badges",
        "selling_method-as-text",
        "iva-as-text",
        "new-unknown-field",
    ],
)
def test_changes_to_unused_fields_still_validate(
    mutate: Callable[[dict[str, dict[str, object]]], object],
) -> None:
    """T2 — 011-mercadona-scraper-upstream-schema-resilience, RF-1/RF-2:
    the cases that broke every search during the spec 011 investigation."""
    hit = _algolia_hit()
    mutate(hit)

    product = RawAlgoliaProduct.model_validate(hit)

    assert product.id == "10381"


def test_unit_price_is_parsed_as_a_number() -> None:
    """T2 — Decision D2: Mercadona sends "5.04"; parsing it in validation
    means a non-numeric price fails here, not later in the mapper."""
    product = RawAlgoliaProduct.model_validate(_algolia_hit())

    assert product.price_instructions.unit_price == 5.04


@pytest.mark.parametrize("bad_value", ["abc", None])
def test_invalid_unit_price_fails_validation(bad_value: object) -> None:
    """T2 — RF-3: unit_price is a used field; an unusable value is a
    validation error (turned into 502 by T3/T4), not a crash later."""
    hit = _algolia_hit()
    hit["price_instructions"]["unit_price"] = bad_value

    with pytest.raises(ValidationError):
        RawAlgoliaProduct.model_validate(hit)


def test_missing_unit_price_fails_validation() -> None:
    hit = _algolia_hit()
    hit["price_instructions"].pop("unit_price")

    with pytest.raises(ValidationError):
        RawAlgoliaProduct.model_validate(hit)


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


def test_raw_algolia_response_requires_at_least_one_result() -> None:
    """T3 — 011, Decision D3: `results` must not be empty, so the client
    never indexes into an empty list."""
    with pytest.raises(ValidationError):
        RawAlgoliaResponse.model_validate({"results": []})
