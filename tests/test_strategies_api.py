from unittest.mock import MagicMock

import pytest
import requests

from mercadona_scraper.exceptions import APISchemaError
from mercadona_scraper.strategies.api import ApiStrategy


def _resp(json_data):
    r = MagicMock()
    r.json.return_value = json_data
    return r


def _http_error(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    exc = requests.HTTPError(f"HTTP {status_code}")
    exc.response = resp
    return exc


# --------------------------------------------------------------------- #
# _all_categories
# --------------------------------------------------------------------- #


def test_all_categories_raises_api_schema_error_when_results_key_missing():
    client = MagicMock()
    client.get.return_value = _resp({"unexpected": "shape"})
    strategy = ApiStrategy("leche", client)

    with pytest.raises(APISchemaError):
        strategy._all_categories("mad1")


def test_all_categories_returns_results_list_when_present():
    client = MagicMock()
    client.get.return_value = _resp({"results": [{"id": 1}, {"id": 2}]})
    strategy = ApiStrategy("leche", client)

    results = strategy._all_categories("mad1")

    assert results == [{"id": 1}, {"id": 2}]


# --------------------------------------------------------------------- #
# _subcategory_products
# --------------------------------------------------------------------- #


def test_subcategory_products_returns_empty_list_on_404():
    client = MagicMock()
    client.get.side_effect = _http_error(404)
    strategy = ApiStrategy("leche", client)

    result = strategy._subcategory_products(111, "mad1")

    assert result == []


def test_subcategory_products_reraises_non_404_http_errors():
    client = MagicMock()
    client.get.side_effect = _http_error(500)
    strategy = ApiStrategy("leche", client)

    with pytest.raises(requests.HTTPError):
        strategy._subcategory_products(111, "mad1")


def test_subcategory_products_flattens_products_with_category_name():
    client = MagicMock()
    client.get.return_value = _resp(
        {
            "categories": [
                {
                    "name": "Aceite de oliva",
                    "products": [{"id": 1, "display_name": "Aceite virgen"}],
                }
            ]
        }
    )
    strategy = ApiStrategy("aceite", client)

    result = strategy._subcategory_products(420, "mad1")

    assert len(result) == 1
    assert result[0]["_category_name"] == "Aceite de oliva"


# --------------------------------------------------------------------- #
# _scan_mid_category
# --------------------------------------------------------------------- #


def test_scan_mid_category_returns_empty_list_on_request_exception(monkeypatch):
    monkeypatch.setattr("mercadona_scraper.strategies.api.time.sleep", lambda s: None)
    client = MagicMock()
    client.get.side_effect = requests.RequestException("network down")
    strategy = ApiStrategy("leche", client)

    result = strategy._scan_mid_category(111, "mad1", "leche")

    assert result == []


def test_scan_mid_category_filters_by_term(monkeypatch):
    monkeypatch.setattr("mercadona_scraper.strategies.api.time.sleep", lambda s: None)
    client = MagicMock()
    client.get.return_value = _resp(
        {
            "categories": [
                {
                    "name": "Leches",
                    "products": [
                        {"id": 1, "display_name": "Leche Entera Hacendado"},
                        {"id": 2, "display_name": "Agua mineral"},
                    ],
                }
            ]
        }
    )
    strategy = ApiStrategy("leche", client)

    result = strategy._scan_mid_category(111, "mad1", "leche")

    assert [p["id"] for p in result] == [1]


# --------------------------------------------------------------------- #
# search() — full aggregation
# --------------------------------------------------------------------- #


def test_search_aggregates_matches_across_nested_categories_case_insensitive(monkeypatch):
    monkeypatch.setattr("mercadona_scraper.strategies.api.time.sleep", lambda s: None)

    def fake_get(url, timeout=15, **kwargs):
        if "categories/?lang=es" in url:
            return _resp(
                {
                    "results": [
                        {"categories": [{"id": 111}, {"id": 112}]},
                        {"categories": [{"id": 113}]},
                    ]
                }
            )
        if "/categories/111/" in url:
            return _resp(
                {
                    "categories": [
                        {
                            "name": "Leches",
                            "products": [
                                {"id": 1, "display_name": "LECHE Entera Hacendado"},
                            ],
                        }
                    ]
                }
            )
        if "/categories/112/" in url:
            return _resp(
                {
                    "categories": [
                        {
                            "name": "Bebidas",
                            "products": [{"id": 2, "display_name": "Agua mineral"}],
                        }
                    ]
                }
            )
        if "/categories/113/" in url:
            return _resp(
                {
                    "categories": [
                        {
                            "name": "Postres",
                            "products": [{"id": 3, "display_name": "Natillas de leche"}],
                        }
                    ]
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    client = MagicMock()
    client.get.side_effect = fake_get
    strategy = ApiStrategy("leche", client)

    matches = strategy.search("mad1")

    matched_ids = sorted(p["id"] for p in matches)
    assert matched_ids == [1, 3]


def test_search_returns_empty_list_and_logs_warning_when_no_matches(caplog):
    import logging

    client = MagicMock()
    client.get.return_value = _resp({"results": []})
    strategy = ApiStrategy("inexistente", client)

    with caplog.at_level(logging.WARNING):
        matches = strategy.search("mad1")

    assert matches == []
    assert any("No se encontró" in rec.message for rec in caplog.records)
