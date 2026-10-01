# Tasks 010 — Operational Robustness

Desglose de [plan.md](plan.md). Orden = orden de dependencia (§5 de plan.md). Cada tarea <30 min y es una unidad de trabajo revisable: TDD estricto activo — cada tarea de comportamiento primero escribe el test en rojo (RED), luego el código mínimo para ponerlo en verde (GREEN), y sólo entonces refactoriza si hace falta, dejando la suite completa en verde al cerrar la tarea (`uv run pytest -q`).

## PR único — tiempos límite y `/ready`

Rama `010-operational-robustness`, base `main`. Estimación: **≈250 líneas** (plan.md §7). La CI de la spec 009 valida el PR antes de fusionar.

- [x] **T1 — `core/config.py`: `REDIS_TIMEOUT_SECONDS` y `HTTP_TIMEOUT_SECONDS`**
  `REDIS_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0)` y `HTTP_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)`.
  RED: `tests/core/test_config.py` — por defecto `1.0` y `5.0`; ambos se sobrescriben por variable de entorno; `0` y `-1` ⇒ `ValidationError` en los dos.
  GREEN: añade los dos campos.
  Depende: —.
  RF: RF-1, RF-4.
  Hecho cuando: los tests nuevos están en verde y la suite completa sigue en verde.

- [x] **T2 — `http_client_factory.py`: timeout explícito y configurable**
  `build_mercadona_http_client(timeout_seconds: float)` crea el cliente con `timeout=httpx.Timeout(timeout_seconds)`; el `lifespan` de `main.py` le pasa `settings.HTTP_TIMEOUT_SECONDS` (D2). Actualiza las dos llamadas existentes de `tests/scrapers/test_http_client_factory.py`, que hoy la llaman sin argumentos.
  RED: `tests/scrapers/test_http_client_factory.py` — `build_mercadona_http_client(3.0).timeout == httpx.Timeout(3.0)`, y las cabeceras de spec 002 (User-Agent del pool, `Accept-Language`, `Referer`, `Origin`) siguen presentes. `tests/test_main.py` — tras el `lifespan`, el `httpx.AsyncClient` de `MercadonaClient` tiene `httpx.Timeout(5.0)` por defecto y `httpx.Timeout(2.0)` con `HTTP_TIMEOUT_SECONDS=2`. `tests/scrapers/test_mercadona_client_retry.py` — `respx` lanzando `httpx.ReadTimeout` en todos los intentos ⇒ `RETRY_MAX_ATTEMPTS` llamadas y error de transporte al final (RF-5; regresión, ya funciona: el timeout es `TransportError`).
  GREEN: cambia la firma y el `lifespan`.
  Depende: T1.
  RF: RF-4, RF-5.
  Hecho cuando: los tests nuevos y actualizados están en verde y la suite completa sigue en verde.

- [ ] **T3 — `main.py`: timeouts en el cliente de Redis**
  `Redis.from_url(settings.REDIS_URL, socket_timeout=t, socket_connect_timeout=t)` con `t = settings.REDIS_TIMEOUT_SECONDS` (D1).
  RED: `tests/test_main.py` — tras el `lifespan`, el cliente de Redis de `app.state.cache_repository` tiene `connection_pool.connection_kwargs["socket_timeout"] == 1.0` y `["socket_connect_timeout"] == 1.0` por defecto, y `0.3` con `REDIS_TIMEOUT_SECONDS=0.3`; `app.state.warehouse_cache_repository` comparte ese mismo cliente.
  GREEN: pasa los dos argumentos.
  Depende: T1.
  RF: RF-1, RF-2.
  Hecho cuando: los tests nuevos están en verde y la suite completa sigue en verde (los dobles `_FreshFakeRedisFactory` y `_BrokenRedisFactory` ya aceptan `**kwargs`).

- [ ] **T4 — `services/cache.py`: `CacheRepository.ping()`**
  `async def ping(self) -> bool`: `PING` a Redis; ante cualquier `RedisError` (incluido `redis.exceptions.TimeoutError`) devuelve `False` y registra un `WARNING` con **solo el tipo de excepción**, nunca `str(exc)` ni la URL (D3, D5).
  RED: `tests/services/test_cache.py` — `ping()` con `fakeredis` ⇒ `True`. `tests/services/test_cache_resilience.py` — con un doble cuyo `ping` lanza `RedisConnectionError("connection refused to rediss://user:secret@host")` ⇒ `False`, un `WARNING` que contiene `ConnectionError` y no contiene `secret` ni `rediss://`; con `redis.exceptions.TimeoutError` ⇒ `False`.
  GREEN: implementa `ping`.
  Depende: —.
  RF: RF-6, RF-7.
  Hecho cuando: los tests nuevos están en verde y la suite completa sigue en verde.

- [ ] **T5 — `main.py`: `GET /ready`**
  Ruta en `main.py`, fuera del router de `/api/v1` (sin `X-API-Key`), con `Depends(get_cache_repository)`: `ping()` `True` ⇒ `200 {"status": "ready"}`; `False` ⇒ `503 {"status": "unavailable", "redis": "unreachable"}` con `JSONResponse` (D3). `/health` no cambia.
  RED: `tests/test_main.py` — sin `X-API-Key` y `dependency_overrides` con `ping` ⇒ `True`: `200 {"status": "ready"}`; con `ping` ⇒ `False`: `503` con ese cuerpo exacto, sin `redis://` ni `rediss://` en la respuesta; `GET /health` sigue en `200` aunque `ping` devuelva `False` (RF-8); `/openapi.json` incluye `/ready`.
  GREEN: añade la ruta.
  Depende: T4.
  RF: RF-6, RF-7, RF-8.
  Hecho cuando: los tests nuevos están en verde y la suite completa sigue en verde.

- [ ] **T6 — Integración: `tests/integration/test_redis_unresponsive.py`**
  Fixture propio (sin el reemplazo de `app.main.Redis` por `fakeredis` del `conftest`): servidor TCP en `127.0.0.1` con `asyncio.start_server` que acepta conexiones y nunca responde; `REDIS_URL` apuntando a él y `REDIS_TIMEOUT_SECONDS=0.2`; app real con su `lifespan`; `change-pc` y Algolia con `respx` (`mock_change_pc`, `algolia_response`) (D4).
  RED/GREEN: `GET /api/v1/products?postal_code=28001&term=leche` ⇒ `200` con productos en menos de 3 s, y al menos un `WARNING` de Redis no disponible en `caplog`; `GET /ready` ⇒ `503`; `GET /health` ⇒ `200`. Verificar que el test **falla sin T3** (con el cliente de Redis sin timeouts, la búsqueda no termina en 3 s) y pasa con T3.
  Depende: T3, T5.
  RF: RF-2, RF-3, RF-7, RF-8; H1, H3.
  Hecho cuando: el fichero está en verde, se ha comprobado que falla sin los timeouts de T3, y la suite completa sigue en verde.

- [ ] **T7 — Docs vivas: `README.md` y `.env.example`**
  `README.md`: `REDIS_TIMEOUT_SECONDS` y `HTTP_TIMEOUT_SECONDS` en la tabla de variables; `/ready` en "Uso de la API" (qué comprueba, `200`/`503`, que es público) y la diferencia con `/health` (vida frente a disponibilidad; el `HEALTHCHECK` de Docker sigue usando `/health`); en "Limitaciones conocidas", la latencia máxima añadida con Redis colgado (hasta unas cuatro veces `REDIS_TIMEOUT_SECONDS` por búsqueda); fila de la spec 010. `.env.example`: `REDIS_TIMEOUT_SECONDS=1.0` y `HTTP_TIMEOUT_SECONDS=5.0` — **lo añade el usuario** (fichero bloqueado por permisos para el agente).
  Depende: T6.
  RF: constitución #9/#10 (docs vivas).
  Hecho cuando: el README recoge los cuatro puntos y el usuario confirma `.env.example`.

- [ ] **T8 — Lint, cobertura y verificación final**
  `uv run ruff check .` y `uv run ruff format --check .` limpios; `uv run pytest -q --cov=app` en verde con cobertura ≥80%. Verificación manual con Docker: contenedor con `REDIS_URL` apuntando a un host inaccesible ⇒ `/health` `200`, `/ready` `503`, y `GET /api/v1/products` (con `X-API-Key`) responde sin colgarse (`502` si Mercadona no es alcanzable desde el contenedor, o `200`; lo que importa es que **termina**). CI de GitHub en verde en el PR.
  Depende: T7.
  RF: criterios de finalización de spec.md.
  Hecho cuando: los tres comandos pasan, la verificación con Docker se confirma y la CI del PR está en verde.

## Trazabilidad RF → tareas

| RF | Descripción (resumen) | Tareas |
|---|---|---|
| RF-1 | Cliente de Redis con timeout de conexión y operación desde `REDIS_TIMEOUT_SECONDS` (1 s) | T1, T3 |
| RF-2 | Redis que no responde a tiempo ⇒ fallo de cache con `WARNING`, la petición continúa | T3, T6 |
| RF-3 | Búsqueda con Redis colgado termina en tiempo acotado | T6, T8 |
| RF-4 | `HTTP_TIMEOUT_SECONDS` (5 s) explícito en el cliente HTTP | T1, T2 |
| RF-5 | Timeout HTTP ⇒ reintentos de spec 002 y `502` | T2 |
| RF-6 | `GET /ready` público que hace `PING` a Redis | T4, T5 |
| RF-7 | `/ready` ⇒ `200 ready` o `503 unavailable`, sin URL ni credenciales | T4, T5, T6 |
| RF-8 | `/health` sin cambios aunque Redis falle | T5, T6 |

Todos los RF-1 a RF-8 quedan cubiertos por al menos una tarea; ninguno queda sin mapear.
