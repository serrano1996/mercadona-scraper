# Tasks 003 — Logging

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

- [ ] **T1 — `Settings.LOG_LEVEL`**
  Nuevo campo en `app/core/config.py`: `LOG_LEVEL: str = "INFO"`, mismo patrón que los campos ya existentes.
  Depende: —.
  RF: soporte de RF-1.
  Hecho cuando: test unitario — `Settings(...)` sin la env var da `"INFO"` por defecto; con la env var puesta, la respeta.

- [ ] **T2 — `core/logging_config.py`: `configure_logging()` + filtro de request-id**
  `configure_logging(level: str) -> None` (usa `logging.basicConfig`, formato con timestamp/nivel/logger/`request_id`/mensaje). `ContextVar[str | None]` para el request-id + `logging.Filter` que inyecta `record.request_id` (valor real si hay contexto de petición activo, `"-"` si no) — instalado en `configure_logging`. Expone una función/context manager para que el middleware (T4) fije el `ContextVar` por petición.
  Depende: —.
  RF: RF-1, soporte de RF-7.
  Hecho cuando: test unitario — `configure_logging("DEBUG")` deja el logger raíz en `DEBUG`; el filtro inyecta `"-"` sin contexto activo y el valor real dentro de un `with` que lo fija.

- [ ] **T3 — `main.py`: llama `configure_logging()` en el `lifespan`**
  Primera línea del `lifespan`, tras construir `settings = Settings()`: `configure_logging(settings.LOG_LEVEL)`.
  Depende: T1, T2.
  RF: RF-1.
  Hecho cuando: la suite de `tests/test_main.py` (T17 de spec 001) sigue en verde; test nuevo confirma que, tras entrar al lifespan con `LOG_LEVEL=DEBUG`, el logger raíz queda en `DEBUG`.

- [ ] **T4 — `middleware/request_logging.py`: `RequestLoggingMiddleware`**
  `BaseHTTPMiddleware` (Starlette): genera un request-id corto por petición, lo fija en el `ContextVar` de T2, loguea `INFO` de inicio (método, ruta, query params) y de fin (status code, duración en ms) alrededor de `call_next`.
  Depende: T2.
  RF: RF-6, RF-7.
  Hecho cuando: test unitario (app mínima + `caplog`) — una petición produce una línea de inicio y una de fin con el mismo `request_id`; dos peticiones distintas tienen `request_id` distintos.

- [ ] **T5 — `main.py`: registra el middleware**
  `app.add_middleware(RequestLoggingMiddleware)` al crear la instancia de `FastAPI`.
  Depende: T3, T4.
  RF: RF-6, RF-7.
  Hecho cuando: la suite existente de `tests/api/` y `tests/integration/` sigue en verde; test nuevo confirma que una petición real a través de la app completa deja las líneas de inicio/fin en `caplog`.

- [ ] **T6 — `main.py`: exception handler global**
  `@app.exception_handler(Exception)`: `logger.exception(...)` (traceback completo) antes de devolver `500` genérico (`{"detail": "Internal server error"}`).
  Depende: T3.
  RF: RF-2.
  Hecho cuando: test — una ruta que lanza una excepción no prevista (mock) produce una línea `ERROR` con traceback en `caplog` y una respuesta `500`.

- [ ] **T7 — `mercadona_client.py`: log `ERROR` en reintentos agotados**
  Justo antes de `raise last_error` (tras el bucle de `_request_with_retry`): `logger.error(...)` con el número de intentos y la URL.
  Depende: —.
  RF: RF-4.
  Hecho cuando: test — tras agotar `RETRY_MAX_ATTEMPTS` con 5xx o 429 persistente, `caplog` contiene una línea `ERROR` (distinta de los `WARNING` por intento ya existentes).

- [ ] **T8 — `mercadona_client.py`: log `ERROR` en `AlgoliaCredentialsUnavailable`**
  Justo antes de `raise AlgoliaCredentialsUnavailable(...)`: `logger.error(...)` con el contexto del bundle que falló.
  Depende: —.
  RF: RF-5.
  Hecho cuando: test — bundle sin credenciales → `caplog` contiene una línea `ERROR` antes de la excepción.

- [ ] **T9 — `api/v1/products.py`: log `ERROR` al traducir a 502**
  Dentro del `except UpstreamUnavailableError as exc:`, antes de `raise HTTPException(502, ...)`: `logger.error(...)` con `postal_code`, `term` y la excepción.
  Depende: —.
  RF: RF-3.
  Hecho cuando: test — `UpstreamUnavailableError` mockeada → `caplog` contiene una línea `ERROR` con `postal_code`/`term` antes de la respuesta `502`.

- [ ] **T10 — Integración: petición real deja logs de inicio/fin con el mismo `request_id`**
  Sobre `tests/integration/` (T18 de spec 001): una petición completa a través de la app real produce ambas líneas en `caplog` con idéntico `request_id`.
  Depende: T5.
  RF: RF-6, RF-7.
  Hecho cuando: test de integración en verde.

- [ ] **T11 — Caso límite: petición con validación fallida (422) también se loguea**
  Petición sin `postal_code` o `term` → Starlette responde `422` sin pasar por `get_products`; el middleware (T4/T5) igualmente registra inicio/fin.
  Depende: T5.
  RF: caso límite de spec.md (RF-6).
  Hecho cuando: test — petición sin `term` → `422` + líneas de inicio/fin en `caplog`.

- [ ] **T12 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que T25/T12 de specs 001/002).
  Depende: T1–T11.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80%.

- [ ] **T13 — Verificación manual**
  Levantar `uvicorn app.main:app`, provocar cada tipo de error (502 por upstream simulado, credenciales de Algolia no encontradas, reintentos agotados — todo simulado, mismo criterio que T13 de spec 002: nunca contra Mercadona real) y confirmar que cada uno deja una línea `ERROR` clara y con contexto suficiente.
  Depende: T12.
  RF: criterio de finalización de spec.md.
  Hecho cuando: los tres escenarios simulados dejan cada uno su línea `ERROR` reconocible en la salida de logs.
