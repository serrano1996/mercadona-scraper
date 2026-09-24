from pydantic import BaseModel, Field


class ProductQuery(BaseModel):
    # [0-9] rather than \d (spec 007 RF-1, Decision D7 in plan.md): \d in
    # Pydantic v2's Rust regex engine also matches non-ASCII digits.
    postal_code: str = Field(pattern=r"^[0-9]{5}$")
    term: str
