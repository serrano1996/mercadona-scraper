import logging
import time

import requests

from config import API_URL
from exceptions import APISchemaError
from http_client import HttpClient
from strategies.base import SearchStrategy

logger = logging.getLogger(__name__)


class ApiStrategy(SearchStrategy):
    
    def __init__(self, term: str, client: HttpClient):
        self._term = term
        self._client = client

    def search(self, warehouse: str) -> list[dict]:
        top_categories = self._all_categories(warehouse)
        term_lower = self._term.lower()
        matched: list[dict] = []
        for top_cat in top_categories:
            for mid_cat in top_cat.get("categories", []):
                mid_id = mid_cat.get("id")
                if mid_id:
                    matched.extend(self._scan_mid_category(mid_id, warehouse, term_lower))
        if not matched:
            logger.warning(
                f"No se encontró '{self._term}' en ninguna categoría del almacén '{warehouse}'. "
                "Prueba un término más general o comprueba que el producto existe en Mercadona."
            )
        else:
            logger.debug(
                f"Escaneo de categorías: {len(matched)} productos encontrados para '{self._term}'"
            )
        return matched

    def _all_categories(self, warehouse: str) -> list[dict]:
        url = f"{API_URL}/categories/?lang=es&wh={warehouse}"
        logger.debug(f"GET {url}")
        r = self._client.get(url, timeout=15)
        data = r.json()
        results = data.get("results")
        if results is None:
            raise APISchemaError(
                "El endpoint de categorías no devolvió el campo 'results'. "
                f"Claves recibidas: {list(data.keys())}. "
                "La API de Mercadona puede haber cambiado su estructura."
            )
        return results

    def _subcategory_products(self, mid_cat_id: int, warehouse: str) -> list[dict]:
        """
        Jerarquía real de categorías en la API de Mercadona:
          Nivel 1 (top):  id=12  "Aceite, especias y salsas"  ← solo en la lista
            Nivel 2 (mid): id=112 "Aceite, vinagre y sal"     ← fetchable individualmente
              Nivel 3 (sub): id=420 "Aceite de oliva"         ← embebido, contiene products[]
        Solo los IDs de nivel 2 son válidos para GET /api/categories/{id}/.
        """
        url = f"{API_URL}/categories/{mid_cat_id}/?lang=es&wh={warehouse}"
        logger.debug(f"GET {url}")
        try:
            r = self._client.get(url, timeout=15)
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                return []
            raise
        products: list[dict] = []
        for sub_cat in r.json().get("categories", []):
            cat_name = sub_cat.get("name", "")
            for product in sub_cat.get("products", []):
                product["_category_name"] = cat_name
                products.append(product)
        return products

    def _scan_mid_category(self, mid_id: int, warehouse: str, term_lower: str) -> list[dict]:
        try:
            products = self._subcategory_products(mid_id, warehouse)
            time.sleep(0.1)
            return [p for p in products if term_lower in p.get("display_name", "").lower()]
        except requests.RequestException as exc:
            logger.warning(
                f"Subcategoría {mid_id} falló ({type(exc).__name__}): {exc}. "
                "Si esto ocurre frecuentemente, el endpoint de categorías puede haber cambiado."
            )
            return []
