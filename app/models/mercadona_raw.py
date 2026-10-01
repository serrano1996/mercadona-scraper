"""Typed mirror of Mercadona's internal (undocumented) search backend shape
(Algolia hits; see Decision D7 in specs/001-mercadona-scraper-mvp/plan.md).

Field types come from live captures (tests/fixtures/mercadona_algolia_hit_sample.json),
not from Mercadona's own docs — there are none. Never expose these models directly
through the public API (see app/models/product.py + app/mappers/), so a Mercadona-side
rename doesn't break our contract silently.
"""

from pydantic import BaseModel


class RawProductBadges(BaseModel):
    is_water: bool
    requires_age_check: bool


class RawPriceInstructions(BaseModel):
    # Typed str | None from the first sample (always null there); a real
    # request during T26's manual verification hit iva=10 (int). Sampling a
    # whole real category confirmed it's always null or int, never a string.
    iva: int | None
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


class RawAlgoliaCategoryNode(BaseModel):
    """Category breadcrumb node as returned by Algolia search hits.

    A self-referential tree: each level nests the next one under its own
    `categories` key, absent entirely at the deepest level (see Decision D7
    in specs/001-mercadona-scraper-mvp/plan.md).
    """

    id: int
    name: str
    level: int
    order: int
    categories: list["RawAlgoliaCategoryNode"] = []


class RawAlgoliaProduct(BaseModel):
    """Product shape as returned by Mercadona's real search backend (Algolia).

    Nested categories, plus brand/score/popularity_score/objectID that
    Algolia adds for search ranking. See Decision D7 in
    specs/001-mercadona-scraper-mvp/plan.md for how these get fetched.
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


class RawAlgoliaSearchResult(BaseModel):
    """One entry of Algolia's `results` array for a search query (spec 008
    RF-6/RF-7, Decision D2 in plan.md): the current page's hits plus the
    real total (`nbHits`) and page count (`nbPages`).

    Both totals are required, with no default (Decision D3): every real
    response carried them when verified live on 2026-09-30 — including an
    out-of-range page and a blank term — so a missing one means Algolia
    changed its contract and must fail loudly, never produce a fake
    total. `nbPages` already reflects Algolia's pagination cap (1000 hits),
    so it can be smaller than ceil(nbHits / hitsPerPage).
    """

    hits: list[RawAlgoliaProduct]
    nbHits: int
    nbPages: int
