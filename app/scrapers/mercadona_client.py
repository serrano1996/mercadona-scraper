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
import re
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.models.mercadona_raw import RawAlgoliaProduct

logger = logging.getLogger(__name__)

_APP_ID_PATTERN = re.compile(r'REACT_APP_ALGOLIA_ID:"([A-Z0-9]{6,12})"')
_API_KEY_PATTERN = re.compile(r'REACT_APP_ALGOLIA_KEY:"([a-f0-9]{20,40})"')
_INDEX_PREFIX_PATTERN = re.compile(r'REACT_APP_ALGOLIA_NAME:"([a-z_]+)"')

_ALGOLIA_HITS_PER_PAGE = 50


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
        """Retry only on 5xx/timeout/connection errors, up to RETRY_MAX_ATTEMPTS,
        with exponential backoff (Decision D1/D2 in plan.md). A 4xx response is
        returned immediately, untouched, for the caller's own raise_for_status()."""
        last_error: Exception
        for attempt in range(self._settings.RETRY_MAX_ATTEMPTS):
            try:
                response = await self._http_client.request(
                    method, url, headers=headers, json=json
                )
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if response.status_code < 500:
                    return response
                last_error = httpx.HTTPStatusError(
                    f"Server error '{response.status_code}' for url '{url}'",
                    request=response.request,
                    response=response,
                )
            is_last_attempt = attempt == self._settings.RETRY_MAX_ATTEMPTS - 1
            if not is_last_attempt:
                delay = self._settings.RETRY_BASE_DELAY * (2**attempt)
                logger.warning("Retrying %s %s after error: %s", method, url, last_error)
                await asyncio.sleep(delay)
        raise last_error
