import logging
import time

import requests

from config import HEADERS

logger = logging.getLogger(__name__)

_NO_ATTEMPTS_MSG = "Sin intentos realizados"


def _status_hint(status: int) -> str:
    if status in (401, 403):
        return " — el endpoint puede requerir autenticación o haber cambiado."
    if status == 404:
        return " — el endpoint puede haber sido eliminado o renombrado."
    if status >= 500:
        return " — error del servidor, puede ser temporal."
    return ""


def _log_http_error(url: str, exc: requests.HTTPError) -> None:
    status = exc.response.status_code
    logger.exception(
        f"HTTP {status} en {url}{_status_hint(status)} "
        f"Respuesta: {exc.response.text[:300]}"
    )


class HttpClient:
    
    def __init__(self, session: requests.Session | None = None):
        if session is None:
            session = requests.Session()
            session.headers.update(HEADERS)
        self._session = session

    def get(self, url: str, *, timeout: int = 15, retries: int = 3, **kwargs) -> requests.Response:
        last_exc: Exception = RuntimeError(_NO_ATTEMPTS_MSG)
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
                _log_http_error(url, exc)
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

    def post(self, url: str, *, timeout: int = 15, retries: int = 3, **kwargs) -> requests.Response:
        last_exc: Exception = RuntimeError(_NO_ATTEMPTS_MSG)
        for attempt in range(1, retries + 1):
            try:
                r = self._session.post(url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.Timeout:
                last_exc = requests.Timeout(f"Timeout de {timeout}s")
                logger.warning(
                    f"[Intento {attempt}/{retries}] Timeout ({timeout}s) en POST: {url}"
                )
            except requests.HTTPError as exc:
                _log_http_error(url, exc)
                raise
            except requests.ConnectionError as exc:
                last_exc = exc
                logger.warning(
                    f"[Intento {attempt}/{retries}] Sin conexión en POST: {url} ({exc})"
                )
            if attempt < retries:
                wait = 2 ** attempt
                logger.info(f"Reintentando en {wait}s…")
                time.sleep(wait)
        raise requests.ConnectionError(
            f"No se pudo conectar a {url} tras {retries} intentos. "
            f"Último error: {last_exc}"
        )

    def put(self, url: str, *, timeout: int = 15, retries: int = 3, **kwargs) -> requests.Response:
        last_exc: Exception = RuntimeError(_NO_ATTEMPTS_MSG)
        for attempt in range(1, retries + 1):
            try:
                r = self._session.put(url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.Timeout:
                last_exc = requests.Timeout(f"Timeout de {timeout}s")
                logger.warning(
                    f"[Intento {attempt}/{retries}] Timeout ({timeout}s) en PUT: {url}"
                )
            except requests.HTTPError as exc:
                _log_http_error(url, exc)
                raise
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
