"""T10 — 003-mercadona-scaper-logging: a real request through the full app
(real lifespan, real middleware stack) leaves matching start/end log lines
sharing the same request_id (spec.md RF-6/RF-7)."""

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from httpx import AsyncClient

from tests.integration.conftest import mock_change_pc

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_URL = "https://tienda.mercadona.es/asset-manifest.json"
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"

FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
BUNDLE_JS_WITH_CREDENTIALS = (
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    'REACT_APP_ALGOLIA_NAME:"products_prod"'
)


async def test_request_leaves_start_and_end_logs_with_matching_request_id(
    client: AsyncClient, respx_mock: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    mock_change_pc(respx_mock)
    respx_mock.get(MANIFEST_URL).mock(
        return_value=httpx.Response(200, json={"main.js": "/v815/static/js/main.35c4c08c.chunk.js"})
    )
    respx_mock.get(BUNDLE_URL).mock(
        return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
    )
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    respx_mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
        return_value=httpx.Response(200, json={"results": [{"hits": [hit]}]})
    )

    with caplog.at_level(logging.INFO):
        response = await client.get(
            "/api/v1/products", params={"postal_code": "28001", "term": "leche"}
        )

    assert response.status_code == 200
    request_logs = [r for r in caplog.records if r.name == "app.middleware.request_logging"]
    assert len(request_logs) == 2
    request_ids = {r.request_id for r in request_logs}
    assert len(request_ids) == 1
    assert next(iter(request_ids)) != "-"
