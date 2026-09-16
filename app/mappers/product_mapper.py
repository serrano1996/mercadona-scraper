from app.models.mercadona_raw import RawAlgoliaProduct, RawPriceInstructions, RawProduct
from app.models.product import ProductOut


def _build_price_format(price_instructions: RawPriceInstructions) -> str | None:
    if price_instructions.bulk_price is not None and price_instructions.reference_format:
        return f"{price_instructions.bulk_price} €/{price_instructions.reference_format}"
    return None


def map_raw_product_to_product_out(raw: RawProduct) -> ProductOut:
    category = raw.categories[0].name if raw.categories else ""

    return ProductOut(
        id=raw.id,
        name=raw.display_name,
        price=float(raw.price_instructions.unit_price),
        price_format=_build_price_format(raw.price_instructions),
        image_url=raw.thumbnail,
        category=category,
    )


def map_raw_algolia_product_to_product_out(raw: RawAlgoliaProduct) -> ProductOut:
    category = raw.categories[0].name if raw.categories else ""

    return ProductOut(
        id=raw.id,
        name=raw.display_name,
        price=float(raw.price_instructions.unit_price),
        price_format=_build_price_format(raw.price_instructions),
        image_url=raw.thumbnail,
        category=category,
    )
