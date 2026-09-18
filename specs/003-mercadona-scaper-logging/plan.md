# Plan 003 — Logging

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan.

## 1. Módulos

```
app/
├── core/
│   ├── config.py               # MODIFICADO: + LOG_LEVEL: str = "INFO"
│   └── logging_config.py       # NUEVO: configure_logging(level) + filtro de request-id (contextvars)
├── middleware/
│   └── request_logging.py      # NUEVO: RequestLoggingMiddleware — genera request-id, loguea inicio/fin de cada petición
├── main.py                     # MODIFICADO: llama configure_logging() al inicio del lifespan, registra el middleware y un exception_handler global
├── api/v1/products.py          # MODIFICADO: log ERROR al traducir UpstreamUnavailableError -> 502
└── scrapers/mercadona_client.py  # MODIFICADO: log ERROR en reintentos agotados y en AlgoliaCredentialsUnavailable
```

Cobertura por RF:
- `logging_config.py`, `config.py` → **RF-1**
- `main.py` (exception handler) → **RF-2**
- `api/v1/products.py` → **RF-3**
- `mercadona_client.py` → **RF-4, RF-5**
- `middleware/request_logging.py`, `main.py` (registro del middleware) → **RF-6, RF-7**

## 2. Modelo de datos

No hay modelos Pydantic nuevos. El único "dato" nuevo es el request-id (string corto, generado por petición, no persistido) — vive en un `ContextVar`, no en un modelo.

## 3. Decisiones de diseño

### D1 — Middleware ASGI para inicio/fin + request-id, no lógica dentro de cada ruta
**Elegido:** un único `RequestLoggingMiddleware` (Starlette `BaseHTTPMiddleware`) envuelve **todas** las peticiones, incluidas las que fallan validación (422) antes de llegar al handler de la ruta.
**Descartado:** loguear inicio/fin manualmente dentro de `get_products` (y de cada ruta futura). Motivo del rechazo: no cubriría las peticiones que fallan validación (Starlette valida antes de entrar al cuerpo de la función), y habría que repetir la misma lógica en cada ruta nueva que se añada más adelante.
RF: **RF-6, RF-7**.

### D2 — Request-id vía `ContextVar` + `logging.Filter`, no como parámetro explícito
**Elegido:** el middleware fija un `ContextVar` al entrar la petición; un `logging.Filter` instalado en el handler raíz (dentro de `configure_logging`) inyecta `record.request_id` automáticamente en **todas** las líneas de log emitidas durante esa petición — incluidas las de módulos que no saben nada de HTTP (`mercadona_client.py`, `cache.py`).
**Descartado:** pasar `request_id` explícitamente como argumento a cada función/`logger.*` que pudiera loguear algo durante una petición. Motivo del rechazo: no escala — obligaría a enhebrar el `request_id` manualmente por toda la cadena de llamadas (`product_search` → `MercadonaClient` → `_request_with_retry`), acoplando código de dominio a una preocupación puramente de logging.
RF: **RF-7**.

### D3 — Exception handler global de FastAPI, no confiar en el logging propio de uvicorn
**Elegido:** `@app.exception_handler(Exception)` registrado en `main.py`, usa `logger.exception(...)` (incluye traceback) antes de devolver `500` genérico.
**Descartado:** dejar que la excepción se propague sin más y confiar en que uvicorn la loguee por su cuenta. Motivo del rechazo: el logging de uvicorn no pasa por nuestra configuración (RF-1: nivel/formato propios) ni incluye el `request_id` de RF-7 — sería inconsistente con el resto de logs de la app.
RF: **RF-2**.

### D4 — Logging síncrono estándar, no un logger async
**Elegido:** llamadas `logger.*` normales y síncronas en todo el código, mismo patrón que los `logger.warning` ya existentes en `cache.py`/`mercadona_client.py`.
**Descartado:** un logger async (`asyncio.Queue` + consumer en background) o una librería como `aiologger`. Motivo del rechazo: complejidad no justificada para el volumen de este proyecto (una API de búsqueda, no un sistema de alto volumen); el coste de escribir a `stderr` es despreciable frente a las llamadas HTTP reales que ya hace cada petición. Documentado como excepción aceptada a la asincronía obligatoria en el NFR de spec.md.
RF: soporte transversal de todos los RF.

### D5 — Un único punto de configuración, llamado una vez dentro del `lifespan`
**Elegido:** `configure_logging(settings.LOG_LEVEL)` se llama una única vez al principio de `lifespan()` en `main.py` (`logging.basicConfig` sólo tiene efecto la primera vez que se invoca en el proceso).
**Descartado:** configurar el logging a nivel de módulo, en el import de `app/main.py`, fuera del `lifespan`. Motivo del rechazo: los tests de integración (T18, spec 001) re-entran el `lifespan` en cada test vía `fastapi_app.router.lifespan_context(fastapi_app)` — configurar dentro del `lifespan` permite que cada test controle su propio `LOG_LEVEL` vía variables de entorno si hace falta, en vez de fijarlo una sola vez al importar el módulo.
RF: **RF-1**.

### D6 — Los logs de RF-4/RF-5 viven junto a la lógica que fallan, no en un módulo de logging aparte
**Elegido:** las líneas `logger.error(...)` de reintentos agotados y credenciales de Algolia no encontradas se añaden directamente en `mercadona_client.py`, junto al `raise` correspondiente — mismo patrón que los `logger.warning` ya existentes en el mismo archivo.
**Descartado:** centralizar todo el logging de errores de dominio en un decorador genérico "loguea cualquier excepción" que envuelva funciones. Motivo del rechazo: sobre-ingeniería para 2 puntos de fallo concretos y ya identificados; un decorador genérico perdería el contexto específico (número de intentos, URL del bundle) que cada `logger.error` necesita para ser útil.
RF: **RF-4, RF-5**.

## 4. Estrategia de test

**Unitarios — `logging_config.py`**
- `configure_logging(level)` fija el nivel del logger raíz correctamente.
- El filtro de request-id inyecta `"-"` cuando no hay contexto de petición activo, y el valor real cuando sí lo hay.

**Unitarios — `RequestLoggingMiddleware`** (con `caplog`)
- Una petición genera una línea `INFO` de inicio y una de fin con `status_code` y duración.
- Dos peticiones (secuenciales en el test) tienen `request_id` distintos.
- Una petición que falla validación (422) también genera las líneas de inicio/fin — caso límite de spec.md.

**Unitarios — `mercadona_client.py`**
- Reintentos agotados → una línea `ERROR` adicional (no sólo los `WARNING` por intento ya existentes), con el número de intentos y la URL.
- `AlgoliaCredentialsUnavailable` → una línea `ERROR` antes de la excepción.

**Unitarios — `product_search.py`/`products.py`**
- `UpstreamUnavailableError` traducida a `502` → una línea `ERROR` con `postal_code`/`term` antes de la respuesta.

**Unitario — exception handler global**
- Una ruta que lanza una excepción no prevista (mock) → `logger.exception` registra el traceback, respuesta `500`.

**Integración** (extiende `tests/integration/`)
- Una petición real de punta a punta deja logs de inicio/fin visibles vía `caplog`, con el mismo `request_id` en ambas líneas.

**Cobertura:** mismo objetivo ≥80% (specs 001/002 alcanzaron 99% real).

## 5. Nota sobre el nivel de log por defecto

`LOG_LEVEL=INFO` por defecto es una decisión de producto razonable (visibilidad de inicio/fin de cada petición sin necesitar `DEBUG`), configurable vía variable de entorno sin tocar código — no bloquea el cierre de esta spec (spec.md no dejó dudas abiertas).
