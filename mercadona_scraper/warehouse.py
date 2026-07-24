import logging
import re

import requests

from config import API_URL, POSTAL_TO_WH
from exceptions import WarehouseError
from http_client import HttpClient

logger = logging.getLogger(__name__)

_POSTAL_CODE_RE = re.compile(r"^\d{5}$")


class WarehouseResolver:

    def __init__(self, postal_code: str, client: HttpClient):
        self._postal_code = postal_code
        self._client = client

    def resolve(self) -> str:
        if not _POSTAL_CODE_RE.fullmatch(self._postal_code):
            raise WarehouseError(
                f"Código postal '{self._postal_code}' no tiene un formato válido "
                "(se esperan 5 dígitos)."
            )

        wh = self._from_retrieve_pc()
        if wh:
            logger.debug(f"Almacén (retrieve-pc): {wh}")
            return wh

        wh = self._from_change_pc()
        if wh:
            logger.debug(f"Almacén (change-pc): {wh}")
            return wh

        prefix = self._postal_code[:2]
        wh = POSTAL_TO_WH.get(prefix)
        if wh:
            logger.debug(f"Almacén (mapeo local, prefijo {prefix}): {wh}")
            return wh

        raise WarehouseError(
            f"Código postal '{self._postal_code}' no reconocido. "
            "Comprueba que sea un código postal español válido."
        )

    def _from_retrieve_pc(self) -> str | None:
        url = f"{API_URL}/postal-codes/actions/retrieve-pc/{self._postal_code}/"
        logger.debug(f"GET {url}")
        try:
            r = self._client.get(url, timeout=15)
        except requests.RequestException as exc:
            logger.debug(
                f"retrieve-pc falló ({type(exc).__name__}): {exc}. "
                "Intentando endpoint change-pc…"
            )
            return None
        if r.status_code == 204:
            wh = r.headers.get("x-customer-wh")
            logger.debug(f"204 — x-customer-wh: {wh}")
            return wh
        return self._extract_wh(r, "close_warehouse")

    def _from_change_pc(self) -> str | None:
        url = f"{API_URL}/postal-codes/actions/change-pc/"
        logger.debug(f"PUT {url}")
        try:
            r = self._client.put(url, json={"new_postal_code": self._postal_code}, timeout=15)
        except requests.RequestException as exc:
            logger.debug(
                f"change-pc falló ({type(exc).__name__}): {exc}. "
                "Usando mapeo local de código postal…"
            )
            return None
        wh = r.headers.get("x-customer-wh")
        if wh:
            return wh
        return self._extract_wh(r, "warehouse")

    def _extract_wh(self, response: requests.Response, json_key: str) -> str | None:
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            logger.warning(f"{json_key}: la respuesta no es JSON válido.")
            return None
        wh = data.get(json_key, {}).get("id")
        if not wh:
            logger.warning(
                f"{json_key}: JSON sin '{json_key}.id' — posible cambio de la API de Mercadona. "
                f"Claves recibidas: {list(data.keys())}"
            )
        return wh
