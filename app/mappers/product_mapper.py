from app.models.mercadona_raw import RawProduct
from app.models.product import ProductOut


def map_raw_product_to_product_out(raw: RawProduct) -> ProductOut:
    price_instructions = raw.price_instructions
    price_format: str | None = None
    if price_instructions.bulk_price is not None and price_instructions.reference_format:
        price_format = f"{price_instructions.bulk_price} €/{price_instructions.reference_format}"

    category = raw.categories[0].name if raw.categories else ""

    return ProductOut(
        id=raw.id,
        name=raw.display_name,
        price=float(price_instructions.unit_price),
        price_format=price_format,
        image_url=raw.thumbnail,
        category=category,
    )
