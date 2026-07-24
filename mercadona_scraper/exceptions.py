class MercadonaScraperError(Exception):
    """Clase base para todos los errores del scraper."""

class WarehouseError(MercadonaScraperError):
    """No se pudo determinar el almacén para el código postal dado."""

class APISchemaError(MercadonaScraperError):
    """La API devolvió una estructura inesperada — posible cambio de API."""


class SearchFailedError(MercadonaScraperError):
    """Ninguna estrategia encontró productos."""
