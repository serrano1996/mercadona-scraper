"""Typed mirror of Mercadona's internal (undocumented) JSON shape.

Field types come from a live capture of https://tienda.mercadona.es/api/categories/72/
(see tests/fixtures/mercadona_product_sample.json), not from Mercadona's own docs —
there are none. Never expose these models directly through the public API (see
app/models/product.py + app/mappers/), so a Mercadona-side rename doesn't break our
contract silently.
"""

from pydantic import BaseModel


class RawCategoryRef(BaseModel):
    id: int
    name: str
    level: int
    order: int


class RawProductBadges(BaseModel):
    is_water: bool
    requires_age_check: bool


class RawPriceInstructions(BaseModel):
    iva: str | None
    is_new: bool
    is_pack: bool
    pack_size: float | None
    unit_name: str | None
    unit_size: float
    # Always present in every sampled product, but nullable per spec.md's
    # "missing price-per-unit" edge case — not every Mercadona product is
    # guaranteed to carry it (see app/mappers/product_mapper.py).
    bulk_price: str | None
    unit_price: str
    approx_size: bool
    size_format: str
    total_units: int | None
    unit_selector: bool
    bunch_selector: bool
    # Always null in every sampled product; real type unverified.
    drained_weight: float | None
    selling_method: int
    tax_percentage: str
    price_decreased: bool
    reference_price: str
    min_bunch_amount: float
    # Same nullability note as bulk_price above.
    reference_format: str | None
    # Sometimes comes with leading whitespace from Mercadona's own API
    # (e.g. "        7.02") — keep raw here, clean up in the mapper (T6).
    previous_unit_price: str | None
    increment_bunch_amount: float


class RawProduct(BaseModel):
    id: str
    slug: str
    limit: int
    badges: RawProductBadges
    # Always null in every sampled product; real type unverified.
    status: str | None
    packaging: str | None
    published: bool
    share_url: str
    thumbnail: str
    categories: list[RawCategoryRef]
    display_name: str
    main_feature: str | None
    # Always null in every sampled product; real type unverified.
    unavailable_from: str | None
    price_instructions: RawPriceInstructions
    # Always empty in every sampled product; element type unverified.
    unavailable_weekdays: list[int]
    is_new_arrival: bool


class RawAlgoliaCategoryNode(BaseModel):
    """Category breadcrumb node as returned by Algolia search hits.

    Unlike RawCategoryRef (flat list from /api/categories/), this is a
    self-referential tree — each level nests the next one under its own
    `categories` key, absent entirely at the deepest level (see Decision D7
    in plan.md).
    """

    id: int
    name: str
    level: int
    order: int
    categories: list["RawAlgoliaCategoryNode"] = []


class RawAlgoliaProduct(BaseModel):
    """Product shape as returned by Mercadona's real search backend (Algolia).

    A distinct shape from RawProduct (category-browse): no main_feature/
    is_new_arrival, nested categories, plus brand/score/popularity_score/
    objectID that Algolia adds for search ranking. See Decision D7 in
    plan.md for how these get fetched.
    """

    id: str
    slug: str
    limit: int
    badges: RawProductBadges
    status: str | None
    packaging: str | None
    published: bool
    share_url: str
    thumbnail: str
    categories: list[RawAlgoliaCategoryNode]
    display_name: str
    unavailable_from: str | None
    price_instructions: RawPriceInstructions
    unavailable_weekdays: list[int]
    # Present for every sampled hit, but a generic/unbranded product is a
    # plausible real-world case we haven't observed — kept nullable.
    brand: str | None
    score: float
    popularity_score: int
    objectID: str
