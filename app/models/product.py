from datetime import datetime

from pydantic import BaseModel


class ProductOut(BaseModel):
    id: str
    name: str
    price: float
    price_format: str | None
    image_url: str
    category: str


class SearchMeta(BaseModel):
    postal_code: str
    term: str
    warehouse: str
    strategy_used: str
    scraped_at: datetime
    # Real total of matches for the search (Algolia nbHits), not the
    # number of products in this page (spec 008 RF-6).
    total_results: int
    page: int
    page_size: int
    # Algolia nbPages: already capped by Algolia's 1000-hit pagination
    # limit, so it can be smaller than ceil(total_results / page_size).
    total_pages: int


class ProductSearchResponse(BaseModel):
    search: SearchMeta
    products: list[ProductOut]
