import logging
from datetime import datetime, timezone

from .models import ProductResult, ScraperResult, SearchMeta

logger = logging.getLogger(__name__)


class ProductFormatter:
    
    @staticmethod
    def map_product(p: dict) -> ProductResult:
        pi = p.get("price_instructions", {})
        if not pi:
            logger.warning(
                f"Producto '{p.get('display_name', p.get('id', '?'))}' sin 'price_instructions'. "
                "La estructura de la API puede haber cambiado."
            )
        try:
            price = float(pi.get("unit_price") or pi.get("bulk_price") or 0)
        except (ValueError, TypeError):
            price = 0.0
        ref_price = pi.get("reference_price") or pi.get("bulk_price") or ""
        ref_format = pi.get("reference_format") or ""
        price_format = f"{ref_price} €/{ref_format}" if ref_format else f"{ref_price} €"
        categories = p.get("categories", [])
        category = p.get("_category_name") or (categories[0]["name"] if categories else "")
        return ProductResult(
            id=str(p.get("id", "")),
            name=p.get("display_name", ""),
            price=price,
            price_format=price_format,
            image_url=p.get("thumbnail", ""),
            category=category,
        )

    @staticmethod
    def format_output(
        raw_products: list[dict],
        warehouse: str,
        postal_code: str,
        term: str,
        strategy_used: str = "api",
    ) -> ScraperResult:
        products = [ProductFormatter.map_product(p) for p in raw_products]
        return ScraperResult(
            search=SearchMeta(
                postal_code=postal_code,
                term=term,
                warehouse=warehouse,
                strategy_used=strategy_used,
                scraped_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                total_results=len(products),
            ),
            products=products,
        )
