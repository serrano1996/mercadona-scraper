import logging

import requests

from .exceptions import APISchemaError, SearchFailedError, WarehouseError  # noqa: F401
from .formatters import ProductFormatter
from .http_client import HttpClient
from .models import ScraperResult
from .strategies.algolia import AlgoliaStrategy
from .strategies.api import ApiStrategy
from .strategies.playwright import PlaywrightStrategy
from .warehouse import WarehouseResolver

logger = logging.getLogger(__name__)

_VALID_STRATEGIES = {"api", "playwright", "auto"}


class MercadonaScraper:
    def __init__(
        self,
        postal_code: str,
        term: str,
        headless: bool = True,
        strategy: str = "api",
        client: HttpClient | None = None,  # inyección opcional para tests
    ):
        if strategy not in _VALID_STRATEGIES:
            raise ValueError(
                f"Estrategia '{strategy}' no reconocida. Usa una de: {sorted(_VALID_STRATEGIES)}."
            )
        self.postal_code = postal_code
        self.term = term
        self.headless = headless
        self.strategy = strategy
        self._client = client or HttpClient()
        self._resolver = WarehouseResolver(postal_code, self._client)
        self._strategy_used: str = strategy

    # ------------------------------------------------------------------ #
    #  API pública                                                        #
    # ------------------------------------------------------------------ #

    def get_warehouse(self) -> str:
        return self._resolver.resolve()

    def format_output(self, raw_products: list[dict], warehouse: str) -> ScraperResult:
        return ProductFormatter.format_output(
            raw_products,
            warehouse,
            self.postal_code,
            self.term,
            self._strategy_used,
        )

    def run(self) -> ScraperResult:
        warehouse = self.get_warehouse()
        raw_products = self._run_strategy(warehouse)
        return self.format_output(raw_products, warehouse)

    # ------------------------------------------------------------------ #
    #  Selección y ejecución de estrategia                                #
    # ------------------------------------------------------------------ #

    def _run_strategy(self, warehouse: str) -> list[dict]:
        if self.strategy == "playwright":
            self._strategy_used = "playwright"
            logger.info("Estrategia: Playwright (navegador Chromium)…")
            return PlaywrightStrategy(self.term, self.postal_code, self.headless).search(warehouse)

        if self.strategy == "api":
            self._strategy_used = "api"
            logger.info("Estrategia: API directa…")
            return self._run_api_with_fallback(warehouse)

        # "auto": API → Playwright fallback
        logger.info("Estrategia: auto (API → Playwright)…")
        try:
            raw = self._run_api_with_fallback(warehouse)
        except APISchemaError as exc:
            logger.warning(
                f"API falló por cambio de esquema ({exc}). Usando Playwright como fallback…"
            )
            raw = []
        if raw:
            self._strategy_used = "api"
            return raw
        logger.info("API sin resultados, usando Playwright como fallback…")
        self._strategy_used = "playwright"
        return PlaywrightStrategy(self.term, self.postal_code, self.headless).search(warehouse)

    def _run_api_with_fallback(self, warehouse: str) -> list[dict]:
        """Intenta Algolia primero; si falla o no hay credenciales, escanea categorías."""
        try:
            results = AlgoliaStrategy(self.term, self._client).search(warehouse)
            if results:
                return results
        except APISchemaError:
            raise
        except (requests.RequestException, ValueError) as exc:
            logger.debug(
                f"Algolia falló ({type(exc).__name__}): {exc}. "
                "Usando escaneo de categorías como fallback…"
            )

        logger.info("Usando escaneo de categorías (puede tardar ~15 segundos)…")
        return ApiStrategy(self.term, self._client).search(warehouse)
