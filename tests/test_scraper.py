from unittest.mock import MagicMock

import pytest
import requests

from exceptions import APISchemaError
from scraper import MercadonaScraper


def _make_scraper(strategy="api", client=None) -> MercadonaScraper:
    return MercadonaScraper(
        postal_code="28001",
        term="leche",
        headless=True,
        strategy=strategy,
        client=client or MagicMock(),
    )


# --------------------------------------------------------------------- #
# __init__
# --------------------------------------------------------------------- #


def test_init_raises_value_error_for_unrecognized_strategy():
    with pytest.raises(ValueError):
        _make_scraper(strategy="not-a-real-strategy")


@pytest.mark.parametrize("strategy", ["api", "playwright", "auto"])
def test_init_accepts_valid_strategies(strategy):
    scraper = _make_scraper(strategy=strategy)
    assert scraper.strategy == strategy


# --------------------------------------------------------------------- #
# _run_strategy — strategy="playwright"
# --------------------------------------------------------------------- #


def test_run_strategy_playwright_calls_playwright_search_directly(monkeypatch):
    scraper = _make_scraper(strategy="playwright")
    mock_cls = MagicMock()
    mock_cls.return_value.search.return_value = [{"id": 1}]
    monkeypatch.setattr("scraper.PlaywrightStrategy", mock_cls)

    result = scraper._run_strategy("mad1")

    assert result == [{"id": 1}]
    assert scraper._strategy_used == "playwright"
    mock_cls.assert_called_once_with("leche", "28001", True)
    mock_cls.return_value.search.assert_called_once_with("mad1")


# --------------------------------------------------------------------- #
# _run_strategy — strategy="api"
# --------------------------------------------------------------------- #


def test_run_strategy_api_calls_run_api_with_fallback(monkeypatch):
    scraper = _make_scraper(strategy="api")
    mock_fallback = MagicMock(return_value=[{"id": 2}])
    monkeypatch.setattr(scraper, "_run_api_with_fallback", mock_fallback)

    result = scraper._run_strategy("mad1")

    assert result == [{"id": 2}]
    assert scraper._strategy_used == "api"
    mock_fallback.assert_called_once_with("mad1")


# --------------------------------------------------------------------- #
# _run_strategy — strategy="auto"
# --------------------------------------------------------------------- #


def test_run_strategy_auto_uses_api_results_when_present(monkeypatch):
    scraper = _make_scraper(strategy="auto")
    monkeypatch.setattr(scraper, "_run_api_with_fallback", MagicMock(return_value=[{"id": 3}]))
    mock_playwright_cls = MagicMock()
    monkeypatch.setattr("scraper.PlaywrightStrategy", mock_playwright_cls)

    result = scraper._run_strategy("mad1")

    assert result == [{"id": 3}]
    assert scraper._strategy_used == "api"
    mock_playwright_cls.assert_not_called()


def test_run_strategy_auto_falls_back_to_playwright_when_api_returns_empty(monkeypatch):
    scraper = _make_scraper(strategy="auto")
    monkeypatch.setattr(scraper, "_run_api_with_fallback", MagicMock(return_value=[]))
    mock_playwright_cls = MagicMock()
    mock_playwright_cls.return_value.search.return_value = [{"id": 4}]
    monkeypatch.setattr("scraper.PlaywrightStrategy", mock_playwright_cls)

    result = scraper._run_strategy("mad1")

    assert result == [{"id": 4}]
    assert scraper._strategy_used == "playwright"


def test_run_strategy_auto_catches_api_schema_error_and_falls_back_to_playwright(monkeypatch):
    """Regression test for a real bug fixed this session:

    Previously, APISchemaError raised by AlgoliaStrategy (surfaced through
    _run_api_with_fallback, which deliberately re-raises APISchemaError
    rather than swallowing it) bypassed "auto" mode's Playwright fallback
    entirely and propagated out of run(). It must instead be caught here and
    treated the same as an empty API result, falling through to Playwright.
    """
    scraper = _make_scraper(strategy="auto")

    mock_algolia_cls = MagicMock()
    mock_algolia_cls.return_value.search.side_effect = APISchemaError("schema changed")
    mock_api_cls = MagicMock()
    mock_playwright_cls = MagicMock()
    mock_playwright_cls.return_value.search.return_value = [{"id": 5}]
    monkeypatch.setattr("scraper.AlgoliaStrategy", mock_algolia_cls)
    monkeypatch.setattr("scraper.ApiStrategy", mock_api_cls)
    monkeypatch.setattr("scraper.PlaywrightStrategy", mock_playwright_cls)

    result = scraper._run_strategy("mad1")

    assert result == [{"id": 5}]
    assert scraper._strategy_used == "playwright"
    # APISchemaError re-raises immediately from _run_api_with_fallback,
    # so the category-scan ApiStrategy fallback must never be invoked.
    mock_api_cls.return_value.search.assert_not_called()


# --------------------------------------------------------------------- #
# _run_api_with_fallback — strategy="api" mode semantics
# --------------------------------------------------------------------- #


def test_run_api_with_fallback_propagates_api_schema_error(monkeypatch):
    scraper = _make_scraper(strategy="api")
    mock_algolia_cls = MagicMock()
    mock_algolia_cls.return_value.search.side_effect = APISchemaError("schema changed")
    monkeypatch.setattr("scraper.AlgoliaStrategy", mock_algolia_cls)

    with pytest.raises(APISchemaError):
        scraper._run_api_with_fallback("mad1")


def test_run_api_with_fallback_falls_back_to_api_strategy_on_request_exception(monkeypatch):
    scraper = _make_scraper(strategy="api")
    mock_algolia_cls = MagicMock()
    mock_algolia_cls.return_value.search.side_effect = requests.RequestException("network down")
    mock_api_cls = MagicMock()
    mock_api_cls.return_value.search.return_value = [{"id": 6}]
    monkeypatch.setattr("scraper.AlgoliaStrategy", mock_algolia_cls)
    monkeypatch.setattr("scraper.ApiStrategy", mock_api_cls)

    result = scraper._run_api_with_fallback("mad1")

    assert result == [{"id": 6}]
    mock_api_cls.return_value.search.assert_called_once_with("mad1")


def test_run_api_with_fallback_falls_back_to_api_strategy_when_algolia_returns_empty(monkeypatch):
    scraper = _make_scraper(strategy="api")
    mock_algolia_cls = MagicMock()
    mock_algolia_cls.return_value.search.return_value = []
    mock_api_cls = MagicMock()
    mock_api_cls.return_value.search.return_value = [{"id": 7}]
    monkeypatch.setattr("scraper.AlgoliaStrategy", mock_algolia_cls)
    monkeypatch.setattr("scraper.ApiStrategy", mock_api_cls)

    result = scraper._run_api_with_fallback("mad1")

    assert result == [{"id": 7}]


# --------------------------------------------------------------------- #
# run() — end to end wiring
# --------------------------------------------------------------------- #


def test_run_wires_resolver_strategy_and_formatter_correctly(monkeypatch):
    scraper = _make_scraper(strategy="api")
    monkeypatch.setattr(scraper._resolver, "resolve", MagicMock(return_value="mad1"))
    mock_algolia_cls = MagicMock()
    mock_algolia_cls.return_value.search.return_value = [
        {
            "id": 1,
            "display_name": "Leche entera",
            "thumbnail": "https://example.com/leche.jpg",
            "price_instructions": {"unit_price": "1.05", "reference_format": "L"},
            "categories": [{"name": "Lácteos"}],
        }
    ]
    monkeypatch.setattr("scraper.AlgoliaStrategy", mock_algolia_cls)

    result = scraper.run()

    assert result.search.postal_code == "28001"
    assert result.search.term == "leche"
    assert result.search.warehouse == "mad1"
    assert result.search.strategy_used == "api"
    assert result.search.total_results == 1
    assert len(result.products) == 1
    assert result.products[0].name == "Leche entera"
    assert result.products[0].price == 1.05
    assert result.products[0].category == "Lácteos"


def test_run_propagates_warehouse_error_from_resolver(monkeypatch):
    from exceptions import WarehouseError

    scraper = _make_scraper(strategy="api")
    monkeypatch.setattr(
        scraper._resolver, "resolve", MagicMock(side_effect=WarehouseError("no warehouse"))
    )

    with pytest.raises(WarehouseError):
        scraper.run()
