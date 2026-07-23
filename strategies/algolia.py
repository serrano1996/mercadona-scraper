import logging
import re
from urllib.parse import quote

import requests

from config import BASE_URL
from exceptions import APISchemaError
from http_client import HttpClient
from strategies.base import SearchStrategy

logger = logging.getLogger(__name__)

MANIFEST_TIMEOUT_S = 10
HOME_PAGE_TIMEOUT_S = 15
BUNDLE_JS_TIMEOUT_S = 30
ALGOLIA_QUERY_TIMEOUT_S = 10
ALGOLIA_HITS_PER_PAGE = 50


class AlgoliaStrategy(SearchStrategy):

    def __init__(self, term: str, client: HttpClient):
        self._term = term
        self._client = client

    def search(self, warehouse: str) -> list[dict]:
        bundle_url = self._get_bundle_url()
        if not bundle_url:
            logger.debug("Algolia omitida: no se encontró el bundle JS de la web.")
            return []
        creds = self._extract_credentials(bundle_url)
        if not creds:
            logger.debug(
                "Algolia omitida: credenciales no encontradas en el bundle JS. "
                "Mercadona puede haber cambiado cómo embebe sus claves."
            )
            return []
        return self._query_algolia(*creds, warehouse)

    def _get_bundle_url(self) -> str | None:
        try:
            manifest_r = self._client.get(f"{BASE_URL}/asset-manifest.json", timeout=MANIFEST_TIMEOUT_S)
            main_js = manifest_r.json().get("main.js")
            if main_js:
                url = BASE_URL + main_js
                logger.debug(f"Bundle JS (asset-manifest): {url}")
                return url
        except (requests.RequestException, ValueError):
            logger.debug("asset-manifest.json no disponible, buscando bundle JS en el HTML…")
        try:
            r = self._client.get(BASE_URL, timeout=HOME_PAGE_TIMEOUT_S)
            match = re.search(r'src="(/[^"]*\b(?:main|runtime)[^"]*\.js)"', r.text)
            if match:
                url = BASE_URL + match.group(1)
                logger.debug(f"Bundle JS (regex HTML): {url}")
                return url
            logger.debug("No se encontró etiqueta <script> con bundle JS en el HTML de la home.")
        except requests.RequestException as exc:
            logger.debug(f"No se pudo obtener la home de Mercadona para extraer el bundle JS: {exc}")
        return None

    def _extract_credentials(self, bundle_url: str) -> tuple[str, str] | None:
        logger.debug(f"GET {bundle_url} (extrayendo credenciales Algolia)")
        try:
            r = self._client.get(bundle_url, timeout=BUNDLE_JS_TIMEOUT_S)
        except requests.RequestException as exc:
            logger.debug(f"No se pudo descargar el bundle JS: {exc}")
            return None
        js = r.text
        app_id_match = re.search(
            r'algolia[Aa]pp(?:lication)?[Ii]d["\s]*[:=]\s*["\']([A-Z0-9]{6,12})["\']', js
        ) or re.search(
            r'"ALGOLIA_[A-Z]*_?APP_[A-Z]*_?ID"\s*:\s*"([A-Z0-9]{6,12})"', js
        )
        api_key_match = re.search(
            r'algolia[Aa]pi[Kk]ey["\s]*[:=]\s*["\']([a-f0-9]{20,40})["\']', js
        ) or re.search(
            r'"ALGOLIA[A-Z_]{0,20}(?:API|SEARCH)[A-Z_]{0,20}KEY"\s*:\s*"([a-fA-F0-9]{20,40})"', js
        )
        if app_id_match and api_key_match:
            logger.debug(f"Credenciales Algolia — appId: {app_id_match.group(1)}")
            return app_id_match.group(1), api_key_match.group(1)
        return None

    def _query_algolia(self, app_id: str, api_key: str, warehouse: str) -> list[dict]:
        index_name = f"products_prod_{warehouse}_es"
        url = f"https://{app_id}-dsn.algolia.net/1/indexes/*/queries"
        headers = {
            "X-Algolia-Application-Id": app_id,
            "X-Algolia-API-Key": api_key,
            "Content-Type": "application/json",
        }
        body = {
            "requests": [
                {
                    "indexName": index_name,
                    "params": (
                        f"query={quote(self._term)}"
                        f"&hitsPerPage={ALGOLIA_HITS_PER_PAGE}&attributesToRetrieve=*"
                    ),
                }
            ]
        }
        logger.debug(f"POST Algolia índice={index_name}")
        r = self._client.post(url, json=body, headers=headers, timeout=ALGOLIA_QUERY_TIMEOUT_S)
        data = r.json()
        results = data.get("results")
        if not results or "hits" not in results[0]:
            raise APISchemaError(
                f"Respuesta de Algolia sin 'results[0].hits'. "
                f"Claves de primer resultado: {list(results[0].keys()) if results else '—'}. "
                "Puede que el índice haya cambiado de nombre o la API de Algolia haya variado."
            )
        hits = results[0]["hits"]
        for h in hits:
            cats = h.get("categories", [])
            h["_category_name"] = cats[0]["name"] if cats else ""
        logger.debug(f"Algolia: {len(hits)} resultados para '{self._term}'")
        return hits
