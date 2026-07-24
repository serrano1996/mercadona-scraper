"""
Unit tests for the pure-logic pieces of PlaywrightStrategy.

Full browser-driven flows (_navigate_and_search, _handle_postal_modal's real
DOM interaction end-to-end, _do_search's real DOM interaction end-to-end,
_extract_dom against a live page) are integration-level behavior that
requires a real (or fully-faked) Chromium browser and are intentionally not
covered here — they would need a real browser / integration test harness.
We DO cover _card_id / _card_image with AsyncMock-based fakes below, since
those are shallow enough to fake reliably.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from mercadona_scraper.strategies.playwright import PlaywrightStrategy


def _strategy(term="leche") -> PlaywrightStrategy:
    return PlaywrightStrategy(term, "28001", headless=True)


# --------------------------------------------------------------------- #
# _parse_price
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "lines,expected",
    [
        (["Leche entera", "1,99 €", "1L"], 1.99),
        (["Producto", "12.50€"], 12.50),
        (["Producto", "0,95 €", "otro texto"], 0.95),
        (["Sin precio aquí"], 0.0),
        ([], 0.0),
        (["100,00 €"], 100.00),
    ],
)
def test_parse_price_extracts_price_from_lines(lines, expected):
    assert PlaywrightStrategy._parse_price(lines) == expected


def test_parse_price_picks_first_matching_line():
    lines = ["Nombre", "PVPR 2,00 €/kg", "1,50 €"]
    # first line matching the price regex wins
    assert PlaywrightStrategy._parse_price(lines) == 2.00


# --------------------------------------------------------------------- #
# _maybe_capture
# --------------------------------------------------------------------- #


def test_maybe_capture_appends_when_term_matches():
    strategy = _strategy("leche")
    product = {"display_name": "Leche Entera Hacendado"}

    strategy._maybe_capture(product, "leche", "Lácteos")

    assert len(strategy._captured) == 1
    assert strategy._captured[0]["_category_name"] == "Lácteos"


def test_maybe_capture_skips_when_term_does_not_match():
    strategy = _strategy("leche")
    product = {"display_name": "Agua mineral"}

    strategy._maybe_capture(product, "leche", "Bebidas")

    assert strategy._captured == []


def test_maybe_capture_is_case_insensitive_via_caller_lowercasing():
    strategy = _strategy("leche")
    product = {"display_name": "LECHE DESNATADA"}

    strategy._maybe_capture(product, "leche", "Lácteos")

    assert len(strategy._captured) == 1


def test_maybe_capture_handles_missing_display_name():
    strategy = _strategy("leche")
    product = {}

    strategy._maybe_capture(product, "leche", "Lácteos")

    assert strategy._captured == []


# --------------------------------------------------------------------- #
# _collect_from_categories
# --------------------------------------------------------------------- #


def test_collect_from_categories_aggregates_matches():
    strategy = _strategy("leche")
    data = {
        "categories": [
            {
                "name": "Leches",
                "products": [
                    {"id": 1, "display_name": "Leche Entera"},
                    {"id": 2, "display_name": "Agua"},
                ],
            },
            {
                "name": "Postres",
                "products": [{"id": 3, "display_name": "Natillas de leche"}],
            },
        ]
    }

    strategy._collect_from_categories(data, "leche")

    ids = sorted(p["id"] for p in strategy._captured)
    assert ids == [1, 3]
    by_id = {p["id"]: p["_category_name"] for p in strategy._captured}
    assert by_id[1] == "Leches"
    assert by_id[3] == "Postres"


def test_collect_from_categories_handles_empty_data():
    strategy = _strategy("leche")

    strategy._collect_from_categories({}, "leche")

    assert strategy._captured == []


# --------------------------------------------------------------------- #
# _collect_from_algolia
# --------------------------------------------------------------------- #


def test_collect_from_algolia_aggregates_matches_and_injects_category():
    strategy = _strategy("leche")
    data = {
        "results": [
            {
                "hits": [
                    {
                        "id": 1,
                        "display_name": "Leche Entera",
                        "categories": [{"name": "Lácteos"}, {"name": "Otro"}],
                    },
                    {"id": 2, "display_name": "Agua", "categories": []},
                ]
            }
        ]
    }

    strategy._collect_from_algolia(data, "leche")

    assert len(strategy._captured) == 1
    assert strategy._captured[0]["id"] == 1
    assert strategy._captured[0]["_category_name"] == "Lácteos"


def test_collect_from_algolia_handles_missing_categories_key():
    strategy = _strategy("leche")
    data = {"results": [{"hits": [{"id": 1, "display_name": "Leche Entera"}]}]}

    strategy._collect_from_algolia(data, "leche")

    assert strategy._captured[0]["_category_name"] == ""


def test_collect_from_algolia_handles_empty_data():
    strategy = _strategy("leche")

    strategy._collect_from_algolia({}, "leche")

    assert strategy._captured == []


# --------------------------------------------------------------------- #
# _card_id / _card_image — shallow AsyncMock-based fakes
# --------------------------------------------------------------------- #


def _fake_locator(count_value, get_attribute_value=None):
    loc = MagicMock()
    loc.first = loc
    loc.count = AsyncMock(return_value=count_value)
    loc.get_attribute = AsyncMock(return_value=get_attribute_value)
    return loc


async def test_card_image_returns_src_when_img_present():
    card = MagicMock()
    card.locator = MagicMock(return_value=_fake_locator(1, "https://example.com/img.jpg"))

    result = await PlaywrightStrategy._card_image(card)

    assert result == "https://example.com/img.jpg"


async def test_card_image_returns_empty_string_when_no_img():
    card = MagicMock()
    card.locator = MagicMock(return_value=_fake_locator(0))

    result = await PlaywrightStrategy._card_image(card)

    assert result == ""


async def test_card_id_returns_data_id_attribute_when_present():
    card = MagicMock()
    card.get_attribute = AsyncMock(side_effect=lambda attr: "123" if attr == "data-id" else None)

    result = await PlaywrightStrategy._card_id(card)

    assert result == "123"


async def test_card_id_falls_back_to_data_product_id():
    card = MagicMock()
    card.get_attribute = AsyncMock(
        side_effect=lambda attr: "456" if attr == "data-product-id" else None
    )

    result = await PlaywrightStrategy._card_id(card)

    assert result == "456"


async def test_card_id_falls_back_to_product_link_href():
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value=None)
    link_locator = _fake_locator(1, "/product/789/leche-entera")
    card.locator = MagicMock(return_value=link_locator)

    result = await PlaywrightStrategy._card_id(card)

    assert result == "789"


async def test_card_id_returns_empty_string_when_nothing_found():
    card = MagicMock()
    card.get_attribute = AsyncMock(return_value=None)
    card.locator = MagicMock(return_value=_fake_locator(0))

    result = await PlaywrightStrategy._card_id(card)

    assert result == ""
