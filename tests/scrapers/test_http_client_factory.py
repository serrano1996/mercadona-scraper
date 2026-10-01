"""T2 — build_mercadona_http_client() fixes a realistic User-Agent once per
client instance and sends headers matching a real browser request to
tienda.mercadona.es (spec.md RF-1, 002-mercadona-scraper-antibaneo)."""

import httpx

from app.scrapers.http_client_factory import USER_AGENTS, build_mercadona_http_client


async def test_user_agent_is_from_the_pool() -> None:
    async with build_mercadona_http_client(5.0) as client:
        assert client.headers["User-Agent"] in USER_AGENTS


async def test_headers_match_a_real_browser_request() -> None:
    async with build_mercadona_http_client(5.0) as client:
        assert client.headers["Accept-Language"] == "es-ES,es;q=0.9"
        assert client.headers["Referer"] == "https://tienda.mercadona.es/"
        assert client.headers["Origin"] == "https://tienda.mercadona.es"


async def test_timeout_is_explicit_and_configurable() -> None:
    """T2 — 010-mercadona-scraper-operational-robustness, RF-4: the
    timeout is declared, not httpx's implicit default, and applies to
    connect, read, write and pool."""
    async with build_mercadona_http_client(3.0) as client:
        assert client.timeout == httpx.Timeout(3.0)
