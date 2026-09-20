"""Client for Mercadona's real product search backend (Algolia).

tienda.mercadona.es/api/ has no server-side text-search endpoint (verified:
6 candidate REST paths all 404 or ignore the query param). The real search
is Algolia — confirmed via the SPA's current JS bundle (algolia-client-js,
x-algolia-* headers) — but that bundle no longer embeds literal credentials
at runtime. A legacy Create-React-App bundle Mercadona still serves
(reachable via /asset-manifest.json, unlinked from the live site) DOES
embed them as literal REACT_APP_ALGOLIA_* values, and those credentials
were confirmed live in production on 2026-09-16 (a real query returned 232
hits for "leche"). See Decision D7 in plan.md.
"""

import asyncio
import logging
import random
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.models.mercadona_raw import RawAlgoliaProduct

logger = logging.getLogger(__name__)

_APP_ID_PATTERN = re.compile(r'REACT_APP_ALGOLIA_ID:"([A-Z0-9]{6,12})"')
_API_KEY_PATTERN = re.compile(r'REACT_APP_ALGOLIA_KEY:"([a-f0-9]{20,40})"')
_INDEX_PREFIX_PATTERN = re.compile(r'REACT_APP_ALGOLIA_NAME:"([a-z_]+)"')

_ALGOLIA_HITS_PER_PAGE = 50

# Upper bound on how long a single retry waits because of a Retry-After
# value, so a disproportionate or malicious value from the server can't
# hang the process indefinitely (spec 002 RF-4).
MAX_RETRY_AFTER_S = 60.0


def _parse_retry_after(value: str | None) -> float | None:
    """Parses a Retry-After header value per the two formats the HTTP
    standard allows: seconds, or an HTTP-date. Returns None if `value` is
    absent or matches neither format (spec 002 RF-2/RF-3, Decision D3)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max((retry_at - datetime.now(UTC)).total_seconds(), 0.0)


def _error_for_response(
    response: httpx.Response, url: str
) -> tuple[Exception, float | None] | None:
    """Returns None when `response` should be returned as-is (success, or a
    4xx other than 429). Otherwise returns the error to raise if retries run
    out, plus the Retry-After-derived delay for a 429 (None for 5xx, which
    falls back to the caller's exponential backoff)."""
    if response.status_code == 429:
        retry_after_delay = _parse_retry_after(response.headers.get("Retry-After"))
        if retry_after_delay is not None:
            retry_after_delay = min(retry_after_delay, MAX_RETRY_AFTER_S)
        error = httpx.HTTPStatusError(
            f"Too Many Requests for url '{url}'", request=response.request, response=response
        )
        return error, retry_after_delay
    if response.status_code < 500:
        return None
    error = httpx.HTTPStatusError(
        f"Server error '{response.status_code}' for url '{url}'",
        request=response.request,
        response=response,
    )
    return error, None


class AlgoliaCredentialsUnavailable(Exception):
    """Raised when the Algolia app id / api key / index prefix can't be
    extracted from Mercadona's legacy bundle (see Decision D7 in plan.md)."""


class MercadonaClient:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._settings = settings

    async def search(self, term: str, warehouse: str) -> list[RawAlgoliaProduct]:
        app_id, api_key, index_prefix = await self._get_algolia_credentials()
        index_name = f"{index_prefix}_{warehouse}_es"

        response = await self._request_with_retry(
            "POST",
            f"https://{app_id}-dsn.algolia.net/1/indexes/*/queries",
            headers={
                "X-Algolia-Application-Id": app_id,
                "X-Algolia-API-Key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "requests": [
                    {
                        "indexName": index_name,
                        "params": (
                            f"query={quote(term)}"
                            f"&hitsPerPage={_ALGOLIA_HITS_PER_PAGE}&attributesToRetrieve=*"
                        ),
                    }
                ]
            },
        )
        response.raise_for_status()
        hits = response.json()["results"][0]["hits"]
        return [RawAlgoliaProduct.model_validate(hit) for hit in hits]

    async def _get_algolia_credentials(self) -> tuple[str, str, str]:
        manifest_response = await self._request_with_retry(
            "GET", f"{self._settings.MERCADONA_BASE_URL}/asset-manifest.json"
        )
        manifest_response.raise_for_status()
        main_js_path = manifest_response.json()["main.js"]

        bundle_response = await self._request_with_retry(
            "GET", f"{self._settings.MERCADONA_BASE_URL}{main_js_path}"
        )
        bundle_response.raise_for_status()
        js = bundle_response.text

        app_id_match = _APP_ID_PATTERN.search(js)
        api_key_match = _API_KEY_PATTERN.search(js)
        index_prefix_match = _INDEX_PREFIX_PATTERN.search(js)
        if not (app_id_match and api_key_match and index_prefix_match):
            raise AlgoliaCredentialsUnavailable(
                "Could not find Algolia credentials in Mercadona's legacy bundle; "
                "it may have been taken down (see Decision D7 in plan.md)."
            )
        return app_id_match.group(1), api_key_match.group(1), index_prefix_match.group(1)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        """Retry on 5xx/timeout/connection errors and on 429 Too Many
        Requests, up to RETRY_MAX_ATTEMPTS (Decision D1/D2 in plan.md 001;
        D2 in plan.md 002 for 429). A 4xx other than 429 is returned
        immediately, untouched, for the caller's own raise_for_status()."""
        last_error: Exception
        for attempt in range(self._settings.RETRY_MAX_ATTEMPTS):
            retry_after_delay: float | None = None
            try:
                response = await self._http_client.request(method, url, headers=headers, json=json)
            except httpx.TransportError as exc:
                last_error = exc
            else:
                outcome = _error_for_response(response, url)
                if outcome is None:
                    return response
                last_error, retry_after_delay = outcome
            is_last_attempt = attempt == self._settings.RETRY_MAX_ATTEMPTS - 1
            if not is_last_attempt:
                base_delay = (
                    retry_after_delay
                    if retry_after_delay is not None
                    else self._settings.RETRY_BASE_DELAY * (2**attempt)
                )
                delay = base_delay + random.uniform(0, self._settings.RETRY_JITTER_MAX_S)
                logger.warning("Retrying %s %s after error: %s", method, url, last_error)
                await asyncio.sleep(delay)
        logger.error(
            "Exhausted %d attempts for %s %s: %s",
            self._settings.RETRY_MAX_ATTEMPTS,
            method,
            url,
            last_error,
        )
        raise last_error
