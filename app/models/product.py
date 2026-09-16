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
    total_results: int


class ProductSearchResponse(BaseModel):
    search: SearchMeta
    products: list[ProductOut]
