import logging
from unittest.mock import MagicMock

import pytest
import requests

from mercadona_scraper.exceptions import WarehouseError
from mercadona_scraper.warehouse import WarehouseResolver


def _response(status_code=200, headers=None, content=b"{}", json_data=None, json_error=None):
    r = MagicMock()
    r.status_code = status_code
    r.headers = headers or {}
    r.content = content
    if json_error is not None:
        r.json.side_effect = json_error
    else:
        r.json.return_value = json_data if json_data is not None else {}
    return r


def _resolver(postal_code="28001", client=None):
    return WarehouseResolver(postal_code, client or MagicMock())


# --------------------------------------------------------------------- #
# Invalid postal code
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("bad_pc", ["2800", "280001", "abcde", "", "2800a", "28 01"])
def test_resolve_rejects_invalid_postal_code_without_any_http_call(bad_pc):
    client = MagicMock()

    with pytest.raises(WarehouseError):
        _resolver(bad_pc, client).resolve()

    client.get.assert_not_called()
    client.put.assert_not_called()


# --------------------------------------------------------------------- #
# Tier 1: retrieve-pc
# --------------------------------------------------------------------- #


def test_resolve_uses_retrieve_pc_204_header():
    client = MagicMock()
    client.get.return_value = _response(status_code=204, headers={"x-customer-wh": "mad1"})

    wh = _resolver(client=client).resolve()

    assert wh == "mad1"
    client.get.assert_called_once()
    client.put.assert_not_called()


def test_resolve_uses_retrieve_pc_200_json_close_warehouse():
    client = MagicMock()
    client.get.return_value = _response(
        status_code=200, json_data={"close_warehouse": {"id": "vlc1"}}
    )

    wh = _resolver(client=client).resolve()

    assert wh == "vlc1"
    client.put.assert_not_called()


# --------------------------------------------------------------------- #
# Tier 2: change-pc fallback
# --------------------------------------------------------------------- #


def test_resolve_falls_back_to_change_pc_header_when_retrieve_pc_fails():
    client = MagicMock()
    client.get.side_effect = requests.RequestException("boom")
    client.put.return_value = _response(status_code=200, headers={"x-customer-wh": "bcn1"})

    wh = _resolver(client=client).resolve()

    assert wh == "bcn1"
    client.put.assert_called_once()


def test_resolve_falls_back_to_change_pc_json_when_retrieve_pc_empty():
    client = MagicMock()
    # retrieve-pc "empty": 200 with no useful id -> None from _extract_wh
    client.get.return_value = _response(status_code=200, json_data={"close_warehouse": {}})
    client.put.return_value = _response(status_code=200, json_data={"warehouse": {"id": "svq1"}})

    wh = _resolver(client=client).resolve()

    assert wh == "svq1"


# --------------------------------------------------------------------- #
# Tier 3: local POSTAL_TO_WH mapping
# --------------------------------------------------------------------- #


def test_resolve_falls_back_to_local_mapping_when_both_apis_fail():
    client = MagicMock()
    client.get.side_effect = requests.RequestException("boom")
    client.put.side_effect = requests.RequestException("boom")

    # prefix "28" -> "mad1" per config.POSTAL_TO_WH
    wh = _resolver("28001", client=client).resolve()

    assert wh == "mad1"


def test_resolve_raises_when_all_tiers_fail_and_prefix_unmapped():
    client = MagicMock()
    client.get.side_effect = requests.RequestException("boom")
    client.put.side_effect = requests.RequestException("boom")

    with pytest.raises(WarehouseError):
        _resolver("99999", client=client).resolve()


# --------------------------------------------------------------------- #
# Malformed JSON: warns but does not raise, falls through to next tier
# --------------------------------------------------------------------- #


def test_resolve_logs_warning_and_continues_on_invalid_json(caplog):
    client = MagicMock()
    client.get.return_value = _response(status_code=200, content=b"not-json", json_error=ValueError("bad json"))
    client.put.return_value = _response(status_code=200, json_data={"warehouse": {"id": "zar1"}})

    with caplog.at_level(logging.WARNING):
        wh = _resolver(client=client).resolve()

    assert wh == "zar1"
    client.put.assert_called_once()
    assert any("no es JSON válido" in rec.message for rec in caplog.records)


def test_resolve_logs_warning_and_continues_when_id_key_missing(caplog):
    client = MagicMock()
    # valid JSON, but missing the expected nested "id"
    client.get.return_value = _response(status_code=200, json_data={"unexpected": "shape"})
    client.put.return_value = _response(status_code=200, json_data={"warehouse": {"id": "alc1"}})

    with caplog.at_level(logging.WARNING):
        wh = _resolver(client=client).resolve()

    assert wh == "alc1"
    client.put.assert_called_once()
    assert any("posible cambio de la API" in rec.message for rec in caplog.records)
