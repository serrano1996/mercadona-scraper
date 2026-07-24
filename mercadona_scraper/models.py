from dataclasses import dataclass, asdict

@dataclass
class ProductResult:
    id: str
    name: str
    price: float
    price_format: str
    image_url: str
    category: str

@dataclass
class SearchMeta:
    postal_code: str
    term: str
    warehouse: str
    strategy_used: str
    scraped_at: str
    total_results: int

@dataclass
class ScraperResult:
    search: SearchMeta
    products: list[ProductResult]

    def to_dict(self) -> dict:
        """Convierte el resultado a dict para serialización JSON."""
        return asdict(self)