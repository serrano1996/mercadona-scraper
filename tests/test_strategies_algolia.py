from unittest.mock import MagicMock, patch

import pytest
import requests

from config import BASE_URL
from exceptions import APISchemaError
from strategies.algolia import AlgoliaStrategy


def _resp(json_data=None, text=""):
    r = MagicMock()
    if json_data is not None:
        r.json.return_value = json_data
    else:
        r.json.side_effect = ValueError("no json")
    r.text = text
    return r


# --------------------------------------------------------------------- #
# _get_bundle_url
# --------------------------------------------------------------------- #


def test_get_bundle_url_succeeds_via_asset_manifest():
    client = MagicMock()
    client.get.return_value = _resp(json_data={"main.js": "/static/js/main.abc123.js"})
    strategy = AlgoliaStrategy("leche", client)

    url = strategy._get_bundle_url()

    assert url == f"{BASE_URL}/static/js/main.abc123.js"
    client.get.assert_called_once()


def test_get_bundle_url_falls_back_to_html_regex_when_manifest_raises():
    def fake_get(url, timeout=None, **kwargs):
        if "asset-manifest.json" in url:
            raise requests.RequestException("404")
        return _resp(text='<script defer="defer" src="/static/js/main.9f8d7c6b.js"></script>')

    client = MagicMock()
    client.get.side_effect = fake_get
    strategy = AlgoliaStrategy("leche", client)

    url = strategy._get_bundle_url()

    assert url == f"{BASE_URL}/static/js/main.9f8d7c6b.js"


def test_get_bundle_url_falls_back_to_html_regex_when_manifest_missing_main_js():
    def fake_get(url, timeout=None, **kwargs):
        if "asset-manifest.json" in url:
            return _resp(json_data={"other.js": "/static/js/other.js"})
        return _resp(text='<script src="/static/js/runtime.xyz.js"></script>')

    client = MagicMock()
    client.get.side_effect = fake_get
    strategy = AlgoliaStrategy("leche", client)

    url = strategy._get_bundle_url()

    assert url == f"{BASE_URL}/static/js/runtime.xyz.js"


def test_get_bundle_url_returns_none_when_both_manifest_and_html_fail():
    client = MagicMock()
    client.get.side_effect = requests.RequestException("network down")
    strategy = AlgoliaStrategy("leche", client)

    url = strategy._get_bundle_url()

    assert url is None


def test_get_bundle_url_returns_none_when_html_has_no_matching_script():
    def fake_get(url, timeout=None, **kwargs):
        if "asset-manifest.json" in url:
            raise requests.RequestException("404")
        return _resp(text="<html><body>no scripts here</body></html>")

    client = MagicMock()
    client.get.side_effect = fake_get
    strategy = AlgoliaStrategy("leche", client)

    url = strategy._get_bundle_url()

    assert url is None


# --------------------------------------------------------------------- #
# _extract_credentials
# --------------------------------------------------------------------- #


def test_extract_credentials_matches_both_patterns():
    js = 'var e={algoliaAppId:"ABCDEF12",algoliaApiKey:"abcdef0123456789abcd"};'
    client = MagicMock()
    client.get.return_value = _resp(text=js)
    strategy = AlgoliaStrategy("leche", client)

    creds = strategy._extract_credentials("https://example.com/main.js")

    assert creds == ("ABCDEF12", "abcdef0123456789abcd")


def test_extract_credentials_matches_alternate_uppercase_key_pattern():
    js = '{"ALGOLIA_APP_ID":"ABCDEF12","ALGOLIA_API_KEY":"abcdef0123456789abcd"}'
    client = MagicMock()
    client.get.return_value = _resp(text=js)
    strategy = AlgoliaStrategy("leche", client)

    creds = strategy._extract_credentials("https://example.com/main.js")

    assert creds == ("ABCDEF12", "abcdef0123456789abcd")


def test_extract_credentials_returns_none_when_app_id_missing():
    js = 'var e={algoliaApiKey:"abcdef0123456789abcd"};'
    client = MagicMock()
    client.get.return_value = _resp(text=js)
    strategy = AlgoliaStrategy("leche", client)

    assert strategy._extract_credentials("https://example.com/main.js") is None


def test_extract_credentials_returns_none_when_api_key_missing():
    js = 'var e={algoliaAppId:"ABCDEF12"};'
    client = MagicMock()
    client.get.return_value = _resp(text=js)
    strategy = AlgoliaStrategy("leche", client)

    assert strategy._extract_credentials("https://example.com/main.js") is None


def test_extract_credentials_returns_none_when_bundle_download_fails():
    client = MagicMock()
    client.get.side_effect = requests.RequestException("boom")
    strategy = AlgoliaStrategy("leche", client)

    assert strategy._extract_credentials("https://example.com/main.js") is None


# --------------------------------------------------------------------- #
# search() — graceful skip paths
# --------------------------------------------------------------------- #


def test_search_returns_empty_list_when_no_bundle_url_found():
    client = MagicMock()
    strategy = AlgoliaStrategy("leche", client)

    with patch.object(strategy, "_get_bundle_url", return_value=None):
        result = strategy.search("mad1")

    assert result == []


def test_search_returns_empty_list_when_no_credentials_found():
    client = MagicMock()
    strategy = AlgoliaStrategy("leche", client)

    with patch.object(strategy, "_get_bundle_url", return_value="https://example.com/main.js"), \
         patch.object(strategy, "_extract_credentials", return_value=None):
        result = strategy.search("mad1")

    assert result == []


def test_search_queries_algolia_when_bundle_and_credentials_found():
    client = MagicMock()
    strategy = AlgoliaStrategy("leche", client)
    expected_hits = [{"id": 1, "_category_name": "Lácteos"}]

    with patch.object(strategy, "_get_bundle_url", return_value="https://example.com/main.js"), \
         patch.object(strategy, "_extract_credentials", return_value=("APPID123456", "abcdef0123456789abcd")), \
         patch.object(strategy, "_query_algolia", return_value=expected_hits) as mock_query:
        result = strategy.search("mad1")

    assert result == expected_hits
    mock_query.assert_called_once_with("APPID123456", "abcdef0123456789abcd", "mad1")


# --------------------------------------------------------------------- #
# _query_algolia
# --------------------------------------------------------------------- #


def test_query_algolia_raises_api_schema_error_when_hits_missing():
    client = MagicMock()
    client.post.return_value = _resp(json_data={"results": [{"nbHits": 0}]})
    strategy = AlgoliaStrategy("leche", client)

    with pytest.raises(APISchemaError):
        strategy._query_algolia("appid", "apikey", "mad1")


def test_query_algolia_raises_api_schema_error_when_results_empty():
    client = MagicMock()
    client.post.return_value = _resp(json_data={"results": []})
    strategy = AlgoliaStrategy("leche", client)

    with pytest.raises(APISchemaError):
        strategy._query_algolia("appid", "apikey", "mad1")


def test_query_algolia_injects_category_name_from_first_category():
    client = MagicMock()
    client.post.return_value = _resp(
        json_data={
            "results": [
                {
                    "hits": [
                        {"id": 1, "categories": [{"name": "Lácteos"}, {"name": "Otro"}]},
                        {"id": 2, "categories": []},
                    ]
                }
            ]
        }
    )
    strategy = AlgoliaStrategy("leche", client)

    hits = strategy._query_algolia("appid", "apikey", "mad1")

    assert hits[0]["_category_name"] == "Lácteos"
    assert hits[1]["_category_name"] == ""
