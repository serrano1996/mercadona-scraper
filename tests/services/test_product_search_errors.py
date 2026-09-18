"""T13 — product_search translates a persistent upstream failure (5xx
exhausted, or a connection/timeout error) into UpstreamUnavailableError,
instead of letting raw httpx exceptions cross the service boundary."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.exceptions import UpstreamUnavailableError
from app.models.query import ProductQuery
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository
from app.services.product_search import search_products


def _settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
    )


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.algolia.net/1/indexes/*/queries")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Server error '{status_code}'", request=request, response=response
    )


async def test_raises_domain_error_after_5xx_retries_exhausted() -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = _http_status_error(503)
    query = ProductQuery(postal_code="28001", term="leche")

    with pytest.raises(UpstreamUnavailableError):
        await search_products(
            query, warehouse="mad1", cache=cache, client=client, settings=_settings()
        )

    cache.set.assert_not_called()


async def test_raises_domain_error_on_connection_failure() -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = httpx.ConnectError("boom")
    query = ProductQuery(postal_code="28001", term="leche")

    with pytest.raises(UpstreamUnavailableError):
        await search_products(
            query, warehouse="mad1", cache=cache, client=client, settings=_settings()
        )


async def test_does_not_mask_a_genuine_4xx_as_upstream_unavailable() -> None:
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = _http_status_error(400)
    query = ProductQuery(postal_code="28001", term="leche")

    with pytest.raises(httpx.HTTPStatusError):
        await search_products(
            query, warehouse="mad1", cache=cache, client=client, settings=_settings()
        )


async def test_raises_domain_error_after_429_retries_exhausted() -> None:
    """T9 (spec 002) — a 429 that MercadonaClient couldn't recover from
    (RETRY_MAX_ATTEMPTS exhausted) is treated the same as an exhausted 5xx:
    the API consumer shouldn't need to know Mercadona/Algolia rate-limited
    us specifically (spec 002 RF-6, Decision D6 in plan.md)."""
    cache = AsyncMock(spec=CacheRepository)
    cache.get.return_value = None
    client = AsyncMock(spec=MercadonaClient)
    client.search.side_effect = _http_status_error(429)
    query = ProductQuery(postal_code="28001", term="leche")

    with pytest.raises(UpstreamUnavailableError):
        await search_products(
            query, warehouse="mad1", cache=cache, client=client, settings=_settings()
        )

    cache.set.assert_not_called()
