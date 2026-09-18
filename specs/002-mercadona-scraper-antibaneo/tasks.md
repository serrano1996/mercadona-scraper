# Tasks 002 — Medidas antibaneo

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

- [x] **T1 — `Settings.RETRY_JITTER_MAX_S`**
  Nuevo campo en `app/core/config.py`, mismo patrón que `RETRY_BASE_DELAY`/`RETRY_MAX_ATTEMPTS`: `RETRY_JITTER_MAX_S: float = 0.3`.
  Depende: —.
  RF: soporte de RF-5.
  Hecho cuando: test unitario — `Settings(...)` sin la env var da `0.3` por defecto; con la env var puesta, la respeta.

- [x] **T2 — `scrapers/http_client_factory.py`: pool de User-Agents + factory**
  `USER_AGENTS: list[str]` (las 6 entradas de spec.md RF-1) y `build_mercadona_http_client() -> httpx.AsyncClient`: elige un UA al azar, construye el cliente con `User-Agent` + `Accept-Language: es-ES,es;q=0.9` + `Referer`/`Origin` de `https://tienda.mercadona.es/`.
  Depende: —.
  RF: RF-1.
  Hecho cuando: test unitario — el `User-Agent` del cliente devuelto está en `USER_AGENTS`; `Accept-Language`/`Referer`/`Origin` presentes con el valor esperado.

- [x] **T3 — `main.py`: usa `build_mercadona_http_client()`**
  Sustituye `httpx.AsyncClient()` a secas en el `lifespan` por `build_mercadona_http_client()` de T2.
  Depende: T2.
  RF: RF-1.
  Hecho cuando: la suite de `tests/test_main.py` (T17 de spec 001) sigue en verde; test nuevo o ampliado confirma que el cliente en `app.state.mercadona_client` usa un `User-Agent` del pool.

- [x] **T4 — `mercadona_client.py`: `_parse_retry_after()` pura**
  Función `_parse_retry_after(value: str | None) -> float | None`: intenta segundos (`float()`), si falla intenta fecha HTTP (`email.utils.parsedate_to_datetime`), si ambos fallan o `value` es `None` devuelve `None`.
  Depende: —.
  RF: RF-2, RF-3.
  Hecho cuando: tests unitarios — segundos válidos, fecha HTTP válida, valor no parseable → `None`, `None` de entrada → `None`.

- [x] **T5 — `mercadona_client.py`: rama `429` en `_request_with_retry`** *(corrige bug real: hoy `429 < 500` se devuelve sin reintentar)*
  Antes del `if status_code < 500: return response` genérico, chequear `status_code == 429` explícitamente: usar `_parse_retry_after` (T4) sobre la cabecera `Retry-After`; si hay valor, ese es el delay base; si no, cae al backoff exponencial ya existente (D1 de plan.md 001). Reintenta igual que cualquier otro error retryable.
  Depende: T4.
  RF: RF-2.
  Hecho cuando: test — `429` con `Retry-After` en segundos reintenta y recupera en el intento siguiente; `429` persistente agota `RETRY_MAX_ATTEMPTS` y propaga `httpx.HTTPStatusError` (429) tras el último intento.

- [x] **T6 — `mercadona_client.py`: tope `MAX_RETRY_AFTER_S = 60`**
  El delay derivado de `Retry-After` (T5) se limita a 60s antes de usarse.
  Depende: T5.
  RF: RF-4.
  Hecho cuando: test — `Retry-After: 120` produce un delay efectivo de 60, no 120.

- [x] **T7 — `mercadona_client.py`: jitter aditivo**
  `delay_final = componente_base + random.uniform(0, settings.RETRY_JITTER_MAX_S)` (T1), aplicado tanto al delay de `429` (T5/T6) como al backoff exponencial ya existente para 5xx/timeout/conexión.
  Depende: T1, T5.
  RF: RF-5.
  Hecho cuando: test con `RETRY_JITTER_MAX_S` fijo y `random.uniform` mockeado — el delay incluye el componente jitter; con `RETRY_JITTER_MAX_S=0` el comportamiento es determinista y la suite de T10 (spec 001) sigue en verde sin modificarla.

- [x] **T8 — Regresión: un 4xx que no es `429` sigue sin reintentar**
  Verificar explícitamente que el cambio de T5 no afecta el resto de 4xx (D2 de plan.md 001).
  Depende: T5.
  RF: NFR (no romper D2 de plan.md 001).
  Hecho cuando: test — `400` → 1 sola llamada, sin retry.

- [x] **T9 — `product_search.py`: `429` agotado → `UpstreamUnavailableError`**
  Amplía la condición existente (`except httpx.HTTPStatusError as exc: if exc.response.status_code >= 500`) a `>= 500 or == 429`.
  Depende: T5.
  RF: RF-6.
  Hecho cuando: test — `client.search` lanza `httpx.HTTPStatusError(429)` → `product_search` lanza `UpstreamUnavailableError` (mismo assert que ya cubre 5xx en T13 de spec 001).

- [ ] **T10 — Integración: `429` con `Retry-After` corto se absorbe, la API responde 200**
  Sobre `tests/integration/` (T18 de spec 001): manifest devuelve `429` con `Retry-After` corto, luego `200` → `GET /api/v1/products` responde `200` final.
  Depende: T3, T7.
  RF: RF-2, RF-3, RF-5.
  Hecho cuando: test de integración en verde.

- [ ] **T11 — Integración: `429` persistente → `502` en la API pública**
  Mismo patrón que el 5xx-agotado de T21 (spec 001), pero con `429`.
  Depende: T9, T10.
  RF: RF-6.
  Hecho cuando: test de integración en verde.

- [ ] **T12 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que T25 de spec 001).
  Depende: T1–T11.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80%.

- [ ] **T13 — Verificación manual (simulada, no contra Mercadona real)**
  Levantar `uvicorn app.main:app`, forzar un `429` simulado (mock local o `respx` apuntando a `localhost`, no a `tienda.mercadona.es`) y confirmar que el scraper espera y reintenta en vez de fallar de inmediato. **No se provoca un 429 real contra Mercadona** — ver sección 5 de plan.md.
  Depende: T12.
  RF: criterio de finalización de spec.md.
  Hecho cuando: la verificación simulada muestra espera + reintento + éxito final, sin generar tráfico real contra Mercadona.
