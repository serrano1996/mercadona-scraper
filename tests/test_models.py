from mercadona_scraper.models import ProductResult, ScraperResult, SearchMeta


def _build_result() -> ScraperResult:
    meta = SearchMeta(
        postal_code="28001",
        term="leche",
        warehouse="mad1",
        strategy_used="api",
        scraped_at="2026-07-24T10:00:00Z",
        total_results=2,
    )
    products = [
        ProductResult(
            id="1",
            name="Leche entera",
            price=1.05,
            price_format="1.05 €/L",
            image_url="https://example.com/1.jpg",
            category="Leche",
        ),
        ProductResult(
            id="2",
            name="Leche desnatada",
            price=0.95,
            price_format="0.95 €/L",
            image_url="https://example.com/2.jpg",
            category="Leche",
        ),
    ]
    return ScraperResult(search=meta, products=products)


def test_to_dict_produces_expected_nested_shape():
    result = _build_result()

    data = result.to_dict()

    assert set(data.keys()) == {"search", "products"}
    assert data["search"] == {
        "postal_code": "28001",
        "term": "leche",
        "warehouse": "mad1",
        "strategy_used": "api",
        "scraped_at": "2026-07-24T10:00:00Z",
        "total_results": 2,
    }
    assert data["products"] == [
        {
            "id": "1",
            "name": "Leche entera",
            "price": 1.05,
            "price_format": "1.05 €/L",
            "image_url": "https://example.com/1.jpg",
            "category": "Leche",
        },
        {
            "id": "2",
            "name": "Leche desnatada",
            "price": 0.95,
            "price_format": "0.95 €/L",
            "image_url": "https://example.com/2.jpg",
            "category": "Leche",
        },
    ]


def test_to_dict_with_empty_products_list():
    meta = SearchMeta(
        postal_code="08001",
        term="pan",
        warehouse="bcn1",
        strategy_used="playwright",
        scraped_at="2026-07-24T10:00:00Z",
        total_results=0,
    )
    result = ScraperResult(search=meta, products=[])

    data = result.to_dict()

    assert data["products"] == []
    assert data["search"]["total_results"] == 0
