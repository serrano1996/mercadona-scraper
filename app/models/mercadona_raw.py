"""Typed mirror of the parts of Mercadona's internal (undocumented) search
backend response (Algolia; see Decision D7 in specs/001-mercadona-scraper-mvp/plan.md)
that this API actually consumes.

Spec 011: only fields the mapper reads are declared. Algolia hits carry many
more (slug, badges, score, popularity_score, objectID...), but validating
them made every search fail whenever Mercadona changed one the API never
uses — verified on 2026-10-01, and Algolia already omits popularity_score
unless attributesToRetrieve=* is sent. Pydantic ignores undeclared fields,
so those changes are now harmless. The full upstream shape stays documented
in tests/fixtures/mercadona_algolia_hit_sample.json (a live capture).

Never expose these models directly through the public API (see
app/models/product.py + app/mappers/), so a Mercadona-side rename doesn't
break our contract silently.
"""

from pydantic import BaseModel


class RawPriceInstructions(BaseModel):
    # Parsed as a number here (Mercadona sends "5.04"), so a non-numeric
    # price fails validation instead of crashing later in the mapper
    # (spec 011 RF-3, Decision D2).
    unit_price: float
    # Nullable: not every product carries a per-unit price (spec 001
    # caso limite "sin precio por unidad"). Used verbatim in price_format.
    bulk_price: str | None
    reference_format: str | None


class RawAlgoliaCategory(BaseModel):
    """Only the name is used (first category of a hit). Algolia nests a
    category tree under `categories`; it's not modelled (spec 011 D1)."""

    name: str


class RawAlgoliaProduct(BaseModel):
    """One Algolia search hit, reduced to the fields mapped to ProductOut."""

    id: str
    display_name: str
    thumbnail: str
    categories: list[RawAlgoliaCategory]
    price_instructions: RawPriceInstructions


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
