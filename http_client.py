import logging
import time

import requests

from config import HEADERS

logger = logging.getLogger(__name__)

class HttpClient:
    
    def __init__(self, session: requests.Session | None = None):
        if session is None:
            session = requests.Session()
            session.headers.update(HEADERS)
        self._session = session

    def get(self, url: str, *, timeout: int = 15, retries: int = 3, **kwargs) -> requests.Response:
        last_exc: Exception = RuntimeError("Sin intentos realizados")
        for attempt in range(1, retries + 1):
            try:
                r = self._session.get(url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.Timeout:
                last_exc = requests.Timeout(f"Timeout de {timeout}s")
                logger.warning(
                    f"[Intento {attempt}/{retries}] Timeout ({timeout}s) conectando a: {url}"
                )
            except requests.HTTPError as exc:
                status = exc.response.status_code
                hint = ""
                if status in (401, 403):
                    hint = " — el endpoint puede requerir autenticación o haber cambiado."
                elif status == 404:
                    hint = " — el endpoint puede haber sido eliminado o renombrado."
                elif status >= 500:
                    hint = " — error del servidor, puede ser temporal."
                logger.exception(
                    f"HTTP {status} en {url}{hint} "
                    f"Respuesta: {exc.response.text[:300]}"
                )
                raise
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning(
                    f"[Intento {attempt}/{retries}] Sin conexión a: {url} ({exc})"
                )
            if attempt < retries:
                wait = 2 ** attempt
                logger.info(f"Reintentando en {wait}s…")
                time.sleep(wait)
        raise requests.ConnectionError(
            f"No se pudo conectar a {url} tras {retries} intentos. "
            "Comprueba tu conexión a Internet o que tienda.mercadona.es esté disponible. "
            f"Último error: {last_exc}"
        )

    def put(self, url: str, *, timeout: int = 15, retries: int = 3, **kwargs) -> requests.Response:
        last_exc: Exception = RuntimeError("Sin intentos realizados")
        for attempt in range(1, retries + 1):
            try:
                r = self._session.put(url, timeout=timeout, **kwargs)
                if r.status_code in (200, 204):
                    return r
                logger.warning(
                    f"PUT {url} → HTTP {r.status_code}. "
                    f"Respuesta: {r.text[:300]}"
                )
                return r
            except requests.Timeout:
                last_exc = requests.Timeout(f"Timeout de {timeout}s")
                logger.warning(
                    f"[Intento {attempt}/{retries}] Timeout ({timeout}s) en PUT: {url}"
                )
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning(
                    f"[Intento {attempt}/{retries}] Sin conexión en PUT: {url} ({exc})"
                )
            if attempt < retries:
                wait = 2 ** attempt
                logger.info(f"Reintentando en {wait}s…")
                time.sleep(wait)
        raise requests.ConnectionError(
            f"No se pudo conectar a {url} tras {retries} intentos. "
            f"Último error: {last_exc}"
        )
