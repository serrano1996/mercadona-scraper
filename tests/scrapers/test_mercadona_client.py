"""T9 — MercadonaClient.search hits Mercadona's real search backend (Algolia),
extracting credentials from a legacy bundle Mercadona still serves (see
Decision D7 in plan.md). All shapes here are real, captured live on
2026-09-16, not fabricated."""

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from app.core.config import Settings
from app.models.mercadona_raw import RawAlgoliaSearchResult
from app.scrapers.mercadona_client import AlgoliaCredentialsUnavailable, MercadonaClient
from tests.fixtures.algolia import algolia_response

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mercadona_algolia_hit_sample.json"

MANIFEST_PAYLOAD = {"main.js": "/v815/static/js/main.35c4c08c.chunk.js"}
BUNDLE_URL = "https://tienda.mercadona.es/v815/static/js/main.35c4c08c.chunk.js"

# Synthetic values, NOT the real production credentials (never commit those
# to a repo) — same character shape/length as what the legacy bundle really
# embeds, so the extraction regex is exercised the same way. Real technique
# verified live against production on 2026-09-16 (see Decision D7 in
# plan.md); this fixture only proves the parsing logic, not liveness.
FAKE_APP_ID = "TESTAPPID12"
FAKE_API_KEY = "0123456789abcdef0123456789abcdef"
FAKE_INDEX_PREFIX = "products_prod"

BUNDLE_JS_WITH_CREDENTIALS = (
    'REACT_APP_AVAILABLE_LANGUAGES:\'["es","ca","en"]\','
    f'REACT_APP_ALGOLIA_ID:"{FAKE_APP_ID}",'
    f'REACT_APP_ALGOLIA_KEY:"{FAKE_API_KEY}",'
    f'REACT_APP_ALGOLIA_NAME:"{FAKE_INDEX_PREFIX}",'
    'REACT_APP_ANALYTICS_DOMAIN:"tienda.mercadona.es"'
)

BUNDLE_JS_WITHOUT_CREDENTIALS = 'REACT_APP_ANALYTICS_DOMAIN:"tienda.mercadona.es"'


@pytest.fixture
def settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


def _algolia_response_with_one_hit() -> dict:
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return algolia_response([hit])


async def test_search_returns_parsed_products(settings: Settings) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        mock.get(BUNDLE_URL).mock(return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS))
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(200, json=_algolia_response_with_one_hit())
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            products = (
                await client.search(term="leche", warehouse="mad1", page=1, page_size=50)
            ).hits

    assert len(products) == 1
    assert products[0].id == "10381"
    assert products[0].display_name == "Leche semidesnatada Hacendado"
    assert products[0].brand == "Hacendado"
    assert products[0].categories[0].name == "Huevos, leche y mantequilla"


async def test_search_sends_correct_algolia_index_and_headers(settings: Settings) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        mock.get(BUNDLE_URL).mock(return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS))
        algolia_route = mock.post(
            f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
        ).mock(return_value=httpx.Response(200, json=_algolia_response_with_one_hit()))

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            await client.search(term="leche", warehouse="mad1", page=1, page_size=50)

    sent_request = algolia_route.calls.last.request
    assert sent_request.headers["X-Algolia-Application-Id"] == FAKE_APP_ID
    assert sent_request.headers["X-Algolia-API-Key"] == FAKE_API_KEY
    body = json.loads(sent_request.content)
    assert body["requests"][0]["indexName"] == f"{FAKE_INDEX_PREFIX}_mad1_es"
    assert "query=leche" in body["requests"][0]["params"]


async def test_second_search_reuses_cached_algolia_credentials(settings: Settings) -> None:
    """T5 — 006-mercadona-scraper-refactor: a second search() on the same
    MercadonaClient instance reuses credentials fetched on the first call
    — no repeat requests to asset-manifest.json/the bundle (spec.md RF-1)."""
    with respx.mock(assert_all_called=True) as mock:
        manifest_route = mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        bundle_route = mock.get(BUNDLE_URL).mock(
            return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
        )
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(200, json=_algolia_response_with_one_hit())
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            await client.search(term="leche", warehouse="mad1", page=1, page_size=50)
            await client.search(term="agua", warehouse="mad1", page=1, page_size=50)

    assert manifest_route.call_count == 1
    assert bundle_route.call_count == 1


async def test_search_retries_once_with_fresh_credentials_after_401(
    settings: Settings,
) -> None:
    """T6 — 006-mercadona-scraper-refactor: Algolia rejecting cached
    credentials (401/403) invalidates the cache and retries once with
    freshly-fetched credentials (spec.md RF-2)."""
    with respx.mock(assert_all_called=True) as mock:
        manifest_route = mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        bundle_route = mock.get(BUNDLE_URL).mock(
            return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS)
        )
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            side_effect=[
                httpx.Response(401, json={"message": "Invalid Application-ID or API key"}),
                httpx.Response(200, json=_algolia_response_with_one_hit()),
            ]
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            products = (
                await client.search(term="leche", warehouse="mad1", page=1, page_size=50)
            ).hits

    assert len(products) == 1
    assert manifest_route.call_count == 2
    assert bundle_route.call_count == 2


async def test_search_still_raises_when_retry_also_gets_401(settings: Settings) -> None:
    """T6 — same final behavior as before this refactor when even the
    fresh credentials are rejected: the HTTPStatusError still propagates
    (spec.md RF-3, no observable behavior change on ultimate failure)."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        mock.get(BUNDLE_URL).mock(return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS))
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(401, json={"message": "Invalid Application-ID or API key"})
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await client.search(term="leche", warehouse="mad1", page=1, page_size=50)

    assert exc_info.value.response.status_code == 401


async def test_search_raises_when_credentials_not_found(settings: Settings) -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        mock.get(BUNDLE_URL).mock(
            return_value=httpx.Response(200, text=BUNDLE_JS_WITHOUT_CREDENTIALS)
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with pytest.raises(AlgoliaCredentialsUnavailable):
                await client.search(term="leche", warehouse="mad1", page=1, page_size=50)


async def test_search_logs_error_when_credentials_not_found(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """T8 — 003-mercadona-scaper-logging: extraction failure leaves an
    ERROR log line naming the bundle URL that failed (spec.md RF-5)."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
            return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
        )
        mock.get(BUNDLE_URL).mock(
            return_value=httpx.Response(200, text=BUNDLE_JS_WITHOUT_CREDENTIALS)
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with caplog.at_level(logging.ERROR):
                with pytest.raises(AlgoliaCredentialsUnavailable):
                    await client.search(term="leche", warehouse="mad1", page=1, page_size=50)

    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_logs) == 1
    assert BUNDLE_URL in error_logs[0].getMessage()


def _mock_credentials(mock: respx.MockRouter) -> None:
    mock.get("https://tienda.mercadona.es/asset-manifest.json").mock(
        return_value=httpx.Response(200, json=MANIFEST_PAYLOAD)
    )
    mock.get(BUNDLE_URL).mock(return_value=httpx.Response(200, text=BUNDLE_JS_WITH_CREDENTIALS))


@pytest.mark.parametrize(("page", "page_size", "algolia_page"), [(1, 50, 0), (3, 20, 2)])
async def test_search_translates_public_page_to_algolia(
    settings: Settings, page: int, page_size: int, algolia_page: int
) -> None:
    """T7 — 008-mercadona-scraper-search-completeness, RF-5: the public
    page is 1-based, Algolia's is 0-based (verified live 2026-09-30)."""
    with respx.mock(assert_all_called=True) as mock:
        _mock_credentials(mock)
        algolia_route = mock.post(
            f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
        ).mock(return_value=httpx.Response(200, json=_algolia_response_with_one_hit()))

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            await client.search(term="leche", warehouse="mad1", page=page, page_size=page_size)

    params = json.loads(algolia_route.calls.last.request.content)["requests"][0]["params"]
    assert f"page={algolia_page}" in params.split("&")
    assert f"hitsPerPage={page_size}" in params.split("&")


async def test_search_returns_real_totals(settings: Settings) -> None:
    """T7 — RF-6/RF-7: search() returns Algolia's real total and page
    count alongside the current page's hits."""
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    with respx.mock(assert_all_called=True) as mock:
        _mock_credentials(mock)
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(200, json=algolia_response([hit], nb_hits=233, nb_pages=5))
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            result = await client.search(term="leche", warehouse="mad1", page=1, page_size=50)

    assert isinstance(result, RawAlgoliaSearchResult)
    assert result.nbHits == 233
    assert result.nbPages == 5
    assert len(result.hits) == 1


async def test_search_fails_loudly_without_algolia_totals(settings: Settings) -> None:
    """T7 — Decision D3: a response without nbHits is a broken upstream
    contract, not a search with an unknown total."""
    hit = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    with respx.mock(assert_all_called=True) as mock:
        _mock_credentials(mock)
        mock.post(f"https://{FAKE_APP_ID}-dsn.algolia.net/1/indexes/*/queries").mock(
            return_value=httpx.Response(200, json={"results": [{"hits": [hit], "nbPages": 1}]})
        )

        async with httpx.AsyncClient() as http_client:
            client = MercadonaClient(http_client, settings)
            with pytest.raises(ValidationError):
                await client.search(term="leche", warehouse="mad1", page=1, page_size=50)
