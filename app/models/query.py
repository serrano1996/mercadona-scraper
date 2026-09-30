from pydantic import BaseModel, Field, field_validator


class ProductQuery(BaseModel):
    # [0-9] rather than \d (spec 007 RF-1, Decision D7 in plan.md): \d in
    # Pydantic v2's Rust regex engine also matches non-ASCII digits.
    postal_code: str = Field(pattern=r"^[0-9]{5}$")
    # Length limits apply to the normalized value (spec 008 RF-1/RF-2): a
    # blank term normalizes to "" and fails min_length instead of fetching
    # Mercadona's whole catalog.
    term: str = Field(min_length=1, max_length=100)
    # 1-based for the public API even though Algolia is 0-based (spec 008
    # RF-5); MercadonaClient translates. Defaults keep the pre-008 behavior
    # of a single first page of 50 (RF-8).
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("term", mode="before")
    @classmethod
    def normalize_term(cls, value: object) -> object:
        """Trim edges, collapse inner whitespace and lowercase (spec 008
        RF-3, Decision D1 in plan.md). Algolia ignores case and repeated
        inner spaces but not edge spaces, so this never worsens a result
        and lets equivalent searches share one cache entry."""
        if isinstance(value, str):
            return " ".join(value.split()).lower()
        return value
