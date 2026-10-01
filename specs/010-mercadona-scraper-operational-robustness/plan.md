# Plan 010 — Operational Robustness

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones y estrategia de test. Numeración de decisiones (D1..) propia de este plan. spec.md no tiene dudas abiertas.

**Hechos verificados el 2026-10-01** con las versiones de `uv.lock`:
- `Redis.from_url(url)` sin argumentos deja `socket_timeout` y `socket_connect_timeout` en `None`. Contra un servidor local que acepta conexiones y no responde, `CacheRepository.get` sigue esperando a los 5 s; con `socket_timeout=0.5, socket_connect_timeout=0.5` devuelve `None` a los 0,50 s y registra el `WARNING` existente.
- `redis.exceptions.TimeoutError` es subclase de `RedisError`: la degradación de `CacheRepository` y `WarehouseCacheRepository` lo captura **sin cambios**. `PING` contra el mismo servidor local, con timeout de 0,2 s, lanza `redis.exceptions.TimeoutError`.
- `httpx.ReadTimeout`, `ConnectTimeout`, `WriteTimeout` y `PoolTimeout` son subclases de `httpx.TransportError`: `_request_with_retry` ya los reintenta y `product_search`/`warehouse_resolver` ya los traducen a `UpstreamUnavailableError` (→ `502`). RF-5 está cubierto por el código actual.
- `httpx.Timeout(5.0)` es igual al timeout por defecto de `httpx.AsyncClient()`: declararlo no cambia el comportamiento (RF-4).
- `fakeredis.FakeAsyncRedis().ping()` devuelve `True`.

## 1. Módulos

```
app/
├── core/
│   └── config.py              # MODIFICADO: + REDIS_TIMEOUT_SECONDS: float = Field(1.0, gt=0)
│                              #             + HTTP_TIMEOUT_SECONDS: float = Field(5.0, gt=0)
├── scrapers/
│   └── http_client_factory.py # MODIFICADO: build_mercadona_http_client(timeout_seconds: float)
├── services/
│   └── cache.py               # MODIFICADO: + CacheRepository.ping() -> bool
└── main.py                    # MODIFICADO: Redis.from_url con timeouts; factoría con timeout;
                               #             + GET /ready
```

Docs: `README.md` (variables nuevas y `/ready`) y `.env.example` (dos variables nuevas; **bloqueado para el agente por permisos**, lo añade el usuario como en la spec 007).

`mercadona_client.py`, `product_search.py`, `warehouse_resolver.py` y la ruta `/api/v1/products` **no cambian**.

Cobertura por RF:
- `config.py` + `main.py` (cliente de Redis) → **RF-1**; `cache.py` (sin cambios de lógica) → **RF-2**; integración → **RF-3**
- `config.py` + `http_client_factory.py` + `main.py` → **RF-4**; código actual + test de regresión → **RF-5**
- `main.py` (`/ready`) + `cache.py` (`ping`) → **RF-6, RF-7**; `/health` sin cambios → **RF-8**

## 2. Modelo de datos

**`Settings`**, dos campos nuevos con validación al arrancar (spec.md, caso límite "mal configurado"):
- `REDIS_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0)`
- `HTTP_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)`

**Respuestas de `GET /ready`** (fuera de `/api/v1`, como `/health`; no forman parte del contrato de productos):
- `200` → `{"status": "ready"}`
- `503` → `{"status": "unavailable", "redis": "unreachable"}`

## 3. Decisiones de diseño

### D1 — Un único `REDIS_TIMEOUT_SECONDS` para conexión y operación, aplicado en `Redis.from_url`
**Elegido:** `Redis.from_url(settings.REDIS_URL, socket_timeout=t, socket_connect_timeout=t)` en el `lifespan`, con `t = settings.REDIS_TIMEOUT_SECONDS`. Un solo punto de creación del cliente, compartido por `CacheRepository`, `WarehouseCacheRepository` y `/ready` (D3), así que los tres respetan el mismo límite sin código adicional.
**Descartado (`asyncio.wait_for` alrededor de cada operación en los repositorios):** duplica el límite en cada método, no cubre la fase de conexión de forma limpia y deja el cliente subyacente sin límite para cualquier uso futuro.
RF: **RF-1, RF-2, RF-3**.

### D2 — `HTTP_TIMEOUT_SECONDS` como parámetro de la factoría, no leído dentro de ella
**Elegido:** `build_mercadona_http_client(timeout_seconds: float)` crea el `httpx.AsyncClient` con `timeout=httpx.Timeout(timeout_seconds)` (conexión, lectura, escritura y pool). El `lifespan` le pasa `settings.HTTP_TIMEOUT_SECONDS`. La factoría sigue sin depender de `Settings`, como hoy.
**Descartado (que la factoría reciba `Settings` entero):** acopla un módulo de bajo nivel a toda la configuración para leer un número.
**Sin cambios en reintentos:** los timeouts de `httpx` ya son `TransportError` (verificado), así que RF-5 se fija solo con un test de regresión.
RF: **RF-4, RF-5**.

### D3 — `/ready` en `main.py` junto a `/health`, usando `CacheRepository.ping()`
**Elegido:** `CacheRepository` gana `async def ping(self) -> bool`, que hace `PING` y devuelve `False` ante cualquier `RedisError` (incluido el timeout de D1), registrando un `WARNING` sin la URL ni el mensaje del error. `GET /ready` se declara en `main.py`, fuera del router de `/api/v1` (sin `X-API-Key`, como `/health`), recibe el repositorio con `Depends(get_cache_repository)` y devuelve `200` o `503` (`JSONResponse`) según el resultado.
`CacheRepository` es quien ya encapsula el acceso a Redis y su degradación; `ping` sigue ese mismo patrón, y la ruta no ve el cliente de Redis.
**Descartado (exponer el cliente de Redis en `AppState` y hacer `PING` en la ruta):** la ruta tendría que conocer `redis-py` y sus excepciones, y habría un tercer sitio con lógica de Redis aparte de los dos repositorios.
**Descartado (`ping` en `WarehouseCacheRepository`):** cualquiera de los dos serviría porque comparten cliente; `CacheRepository` es el original y el más genérico.
RF: **RF-6, RF-7, RF-8**.

### D4 — Prueba de "Redis colgado" con un servidor TCP local, no con un doble
**Elegido:** un fixture que levanta con `asyncio.start_server` un servidor en `127.0.0.1` que acepta conexiones y nunca responde, y apunta `REDIS_URL` a él con `REDIS_TIMEOUT_SECONDS` bajo (0,2 s) para que el test sea rápido. Se usa el cliente de `redis-py` real, así que se prueba de verdad que los timeouts están configurados en el cliente que crea la app. No sale a la red: el servidor es local y Mercadona/Algolia se simulan con `respx` como siempre.
**Descartado (`AsyncMock` cuyo `get` tarda para siempre):** probaría la lógica de los repositorios, pero no que `Redis.from_url` reciba los timeouts, que es justo el fallo encontrado.
RF: **RF-2, RF-3, RF-7**.

### D5 — Log del fallo de `/ready` sin datos sensibles
**Elegido:** el `WARNING` de `ping()` incluye solo el tipo de excepción (`TimeoutError`, `ConnectionError`), nunca `str(exc)` ni la URL, porque con Upstash la URL lleva la contraseña y algunos mensajes de `redis-py` incluyen host y puerto.
RF: **RF-7**; NFR "Sin secretos en logs ni respuestas".

## 4. Estrategia de test

Todo sin Redis ni Mercadona reales: `fakeredis`, dobles con `side_effect`, el servidor local de D4 y `respx`.

**RF-1 / RF-4 — `tests/core/test_config.py`**
- Valores por defecto: `REDIS_TIMEOUT_SECONDS == 1.0`, `HTTP_TIMEOUT_SECONDS == 5.0`; ambos se sobrescriben por variable de entorno.
- `0` y negativos se rechazan con `ValidationError`.

**RF-4 — `tests/scrapers/test_http_client_factory.py`**
- `build_mercadona_http_client(3.0).timeout == httpx.Timeout(3.0)`; las cabeceras de spec 002 siguen igual.

**RF-1 / RF-4 — `tests/test_main.py`**
- Tras el `lifespan`, el cliente de Redis compartido por los repositorios tiene `socket_timeout` y `socket_connect_timeout` iguales a `REDIS_TIMEOUT_SECONDS`, y el `httpx.AsyncClient` de `MercadonaClient` tiene `httpx.Timeout(HTTP_TIMEOUT_SECONDS)`.

**RF-5 — `tests/scrapers/test_mercadona_client_retry.py`**
- `respx` lanza `httpx.ReadTimeout` en todos los intentos ⇒ se reintenta `RETRY_MAX_ATTEMPTS` veces y termina en error de transporte (regresión: ya funciona).

**RF-6 / RF-7 — `tests/services/test_cache.py` y `tests/services/test_cache_resilience.py`**
- `ping()` con `fakeredis` ⇒ `True`.
- `ping()` con un doble que lanza `RedisConnectionError` o `redis.exceptions.TimeoutError` ⇒ `False`, un `WARNING` con el tipo de excepción y sin el texto del error.

**RF-6 / RF-7 / RF-8 — `tests/test_main.py`**
- `GET /ready` sin `X-API-Key` con Redis disponible (`dependency_overrides` con `ping` → `True`) ⇒ `200 {"status": "ready"}`.
- Con `ping` → `False` ⇒ `503 {"status": "unavailable", "redis": "unreachable"}`, y el cuerpo no contiene `redis://` ni `rediss://`.
- `GET /health` sigue respondiendo `200` aunque `ping` devuelva `False` (RF-8).

**RF-2 / RF-3 / RF-7 — `tests/integration/test_redis_unresponsive.py`** (nuevo, D4)
- App real + `lifespan` con `REDIS_URL` apuntando al servidor local colgado y `REDIS_TIMEOUT_SECONDS=0.2`; `change-pc` y Algolia con `respx`.
- `GET /api/v1/products` ⇒ `200` con productos, en menos de un límite holgado (p. ej. 3 s: hasta cuatro operaciones de cache × 0,2 s más margen), y `WARNING` de Redis no disponible en los logs.
- `GET /ready` ⇒ `503`; `GET /health` ⇒ `200`.

## 5. Secuencia de implementación (base de tasks.md)

1. `Settings`: los dos campos con validación.
2. `build_mercadona_http_client(timeout_seconds)` y su uso en el `lifespan`; test de regresión de `ReadTimeout` (RF-5).
3. Timeouts en `Redis.from_url` del `lifespan` (test de `test_main.py`).
4. `CacheRepository.ping()`.
5. `GET /ready`.
6. Integración con el servidor local colgado.
7. Docs: `README.md` (variables, `/ready`, diferencia con `/health`) y `.env.example` (lo añade el usuario).
8. Lint, formato, cobertura y verificación manual con Docker (contenedor con Redis inaccesible: `/health` 200, `/ready` 503, búsqueda sin colgarse) y CI de GitHub en verde.

## 6. Riesgos y notas

- **Falsos fallos de cache con una red lenta:** con 1 s, un Redis lento (no caído) que tarde más dará fallos de cache y más llamadas a Mercadona. Es configurable (`REDIS_TIMEOUT_SECONDS`) y se documenta.
- **Latencia acotada, no pequeña:** con Redis colgado, una búsqueda puede añadir hasta ~4 s con el valor por defecto (spec.md, Casos límite). Un circuit breaker lo reduciría; queda fuera de alcance.
- **Test de integración con tiempos reales:** usa un servidor TCP local y espera timeouts reales de 0,2 s; el límite del test (3 s) deja margen para una CI lenta. Si diera problemas de estabilidad en GitHub Actions, se sube el margen, no el timeout.
- **`.env.example` bloqueado** por los permisos del agente: el usuario añade `REDIS_TIMEOUT_SECONDS=1.0` y `HTTP_TIMEOUT_SECONDS=5.0`.
- **`/ready` público:** revela si Redis está disponible, nada más; mismo criterio que `/health` (spec 004 dejó públicos `/docs`, `/openapi.json` y `/health`).

## 7. Estimación de líneas cambiadas

| Bloque | Líneas (≈) |
|---|---|
| Código de producción (`config`, `http_client_factory`, `cache`, `main`) | 50 |
| Tests nuevos (config, factoría, `main`, cache, regresión de timeout, integración) | 180 |
| Docs (`README.md`, `.env.example`) | 20 |
| **Total** | **≈ 250** |

Por debajo del presupuesto de 400 líneas: **un único PR**, que la CI de la spec 009 validará antes de fusionar.
