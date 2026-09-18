"""Builds the httpx.AsyncClient MercadonaClient sends its requests through,
with a fingerprint that looks like a real browser hitting
tienda.mercadona.es (spec 002-mercadona-scraper-antibaneo, RF-1).

The User-Agent is chosen once per client instance, not per request —
rotating it mid-session would itself be a stronger bot signal than using
a single fixed one, since a real browser keeps the same UA for its whole
session (see Decision D1 in specs/002-mercadona-scraper-antibaneo/plan.md).
"""

import random

import httpx

USER_AGENTS: list[str] = [
    # Chrome / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Edge / Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Edg/130.0.0.0 Safari/537.36",
    # Safari / macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    # Chrome / Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

_ACCEPT_LANGUAGE = "es-ES,es;q=0.9"
_ORIGIN = "https://tienda.mercadona.es"
_REFERER = "https://tienda.mercadona.es/"


def build_mercadona_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": _ACCEPT_LANGUAGE,
            "Referer": _REFERER,
            "Origin": _ORIGIN,
        }
    )
