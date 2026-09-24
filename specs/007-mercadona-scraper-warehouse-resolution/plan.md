# Plan 007 — Warehouse Resolution

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan; las referencias a decisiones de otros specs se citan como "Dx de plan.md 00N". spec.md no tiene dudas abiertas; este plan no reabre ninguna. Cierra la Decisión D8 de plan.md 001 (warehouse fijo `mad1`, "simplificación temporal, no la solución final").

## 1. Módulos

```
app/
├── core/
│   ├── config.py              # MODIFICADO: + WAREHOUSE_CACHE_TTL_SECONDS: int = 86400
│   │                          #             + WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS: int = 3600
│   ├── state.py               # MODIFICADO: AppState + warehouse_cache_repository: WarehouseCacheRepository
│   └── dependencies.py        # MODIFICADO: + get_warehouse_cache_repository(request)
├── models/
│   └── query.py               # MODIFICADO: postal_code: str = Field(pattern=r"^[0-9]{5}$")
├── exceptions.py              # MODIFICADO: + PostalCodeNotServedError
├── scrapers/
│   └── mercadona_client.py    # MODIFICADO: + resolve_warehouse(postal_code) -> str | None
│                              #             + WarehouseHeaderMissing (mismo patrón que AlgoliaCredentialsUnavailable)
├── services/
│   ├── cache.py               # MODIFICADO: + WarehouseCacheRepository (+ CachedWarehouse), junto a CacheRepository
│   ├── warehouse_resolver.py  # NUEVO: resolve_warehouse(postal_code, cache, client, settings) -> str
│   └── product_search.py      # MODIFICADO: clave search:{warehouse}:{term} (una línea)
├── api/v1/
│   └── products.py            # MODIFICADO: borra _DEFAULT_WAREHOUSE; query: Annotated[ProductQuery, Query()];
│                              #             resuelve almacén antes de buscar; mapea 404 / 502
└── main.py                    # MODIFICADO: lifespan asigna app.state.warehouse_cache_repository (mismo Redis)
```

Docs (docs vivas, constitución #9/#10): `README.md` (tabla de variables + borrar la limitación "Resolución de almacén provisional" + ejemplo de respuesta) y `.env.example` (dos variables nuevas, con sus valores por defecto).

`http_client_factory.py` **no cambia**: la petición `change-pc` sale por el mismo `httpx.AsyncClient` con la huella de navegador de spec 002.

Cobertura por RF:
- `query.py`, `products.py` (firma con `Query()`) → **RF-1**
- `mercadona_client.py` (`resolve_warehouse`) → **RF-2, RF-8 (reintentos), RF-9 (sin reintento), RF-10 (detección)**
- `cache.py` (`WarehouseCacheRepository`), `config.py` → **RF-3, RF-4, RF-11**
- `warehouse_resolver.py` → **RF-2, RF-3, RF-4, RF-8, RF-9, RF-10, RF-11, RF-12**
- `products.py`, `dependencies.py`, `state.py`, `main.py` → **RF-5, RF-8, RF-9, RF-10 (mapeo HTTP)**
- `product_search.py` → **RF-6, RF-7**

## 2. Modelo de datos

**Contrato público sin cambios** (NFR "Compatibilidad de contrato"): `ProductSearchResponse`, `SearchMeta` y `ProductOut` conservan sus campos. Sólo cambia el *valor* de `SearchMeta.warehouse` (almacén real, no `"mad1"`).

**`ProductQuery` (Pydantic v2, I/O de la API):**
- `postal_code: str = Field(pattern=r"^[0-9]{5}$")` — ver D7 sobre `[0-9]` frente a `\d`.
- `term: str` sin cambios.

**`Settings`** gana dos enteros con el mismo patrón de nombres que `CACHE_TTL_SECONDS`:
- `WAREHOUSE_CACHE_TTL_SECONDS: int = 86400` (RF-3).
- `WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS: int = 3600` (RF-11).

**`CachedWarehouse`** (dataclass `frozen`, estado interno, no I/O externo, así que no es Pydantic; mismo criterio que `AppState` en plan.md 006 §2):
```python
@dataclass(frozen=True)
class CachedWarehouse:
    warehouse: str | None   # None = código postal cacheado como "sin servicio" (RF-11)
```

**Claves Redis nuevas** (D3):

| Clave | Valor | TTL | RF |
|---|---|---|---|
| `postal-code-wh:{postal_code}` | id de almacén (`mad3`, `4701`…) como texto UTF-8 | `WAREHOUSE_CACHE_TTL_SECONDS` | RF-3, RF-4 |
| `postal-code-wh-unserved:{postal_code}` | `"1"` (marcador; el valor no se interpreta) | `WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS` | RF-11 |
| `search:{warehouse}:{term}` (antes `search:{postal_code}:{term}`) | `ProductSearchResponse` JSON, sin cambios | `CACHE_TTL_SECONDS` | RF-6 |

## 3. Decisiones de diseño

### D1 — Llamada HTTP en `MercadonaClient`, cache y decisión de dominio en un servicio nuevo `app/services/warehouse_resolver.py`
**Elegido:** dos piezas con responsabilidades separadas, igual que la búsqueda de productos hoy (`MercadonaClient.search` + `services/product_search.search_products`):
- `MercadonaClient.resolve_warehouse(postal_code: str) -> str | None` (capa `scrapers/`, "clientes de endpoints de Mercadona" según `CLAUDE.md`): hace `PUT {MERCADONA_BASE_URL}/api/postal-codes/actions/change-pc/` con `json={"new_postal_code": postal_code}` **a través de `_request_with_retry`**, devuelve el valor de `x-customer-wh` si hay `2xx`, `None` si hay `404`, lanza `WarehouseHeaderMissing` si hay `2xx` sin la cabecera, y deja que `response.raise_for_status()` lance para cualquier otro código. No sabe nada de Redis.
- `resolve_warehouse(postal_code, cache, client, settings) -> str` (capa `services/`, función de módulo con dependencias por parámetro, mismo estilo que `search_products`): consulta el cache, llama al cliente si no hay entrada, escribe la entrada positiva o negativa, traduce a excepciones de dominio (D4) y registra los logs de RF-12.

**Descartado (todo dentro de `MercadonaClient`: HTTP + cache de Redis):** tiene la ventaja de que un único objeto resuelve y cachea, y de que la ruta no necesita una dependencia más. Motivo del rechazo: `MercadonaClient` hoy no conoce Redis (su único estado es la cache **en memoria** de credenciales, D1 de plan.md 006). Meter el `CacheRepository` dentro lo convierte en cliente HTTP y repositorio a la vez, y obliga a que sus tests unitarios (`tests/scrapers/`, sólo respx) monten también fakeredis. Además rompería la simetría con la búsqueda de productos, donde la cache vive en el servicio.
**Descartado (resolver independiente con su propio `httpx.AsyncClient` y su propia lógica de reintento):** el NFR "Reutiliza política anti-baneo existente" prohíbe explícitamente "una política de reintentos paralela y distinta", y `_request_with_retry` es un método privado de `MercadonaClient`. Sacarlo a un módulo compartido es un refactor que este spec no necesita.
**Coste asumido:** la ruta pasa a llamar a dos servicios en secuencia (`resolve_warehouse` y luego `search_products`).
RF: **RF-2, RF-4, RF-5**.

### D2 — Inyección: provider `get_warehouse_cache_repository` en `app/core/dependencies.py` + llamada explícita al servicio en la ruta, no un `Depends` que resuelva el almacén
**Elegido:** mismo patrón de spec 006: el `lifespan` crea `WarehouseCacheRepository(redis_client)` sobre **el mismo** `redis_client` que ya usa `CacheRepository` y lo asigna a `app.state.warehouse_cache_repository`; `AppState` gana ese campo tipado; `dependencies.py` añade `get_warehouse_cache_repository(request)`; `products.py` declara `WarehouseCacheDep = Annotated[WarehouseCacheRepository, Depends(get_warehouse_cache_repository)]` y lo reexporta en `__all__` (D5 de plan.md 006). Dentro de `get_products` se hace `warehouse = await resolve_warehouse(...)` y luego `search_products(query, warehouse=warehouse, ...)` en el mismo bloque `try`.
**Descartado (dependencia FastAPI `ResolvedWarehouse = Annotated[str, Depends(get_resolved_warehouse)]`):** es más declarativo, pero mueve la lógica de error a una dependencia que tendría que lanzar `HTTPException` por su cuenta, separada del `except UpstreamUnavailableError` de la ruta. Resultado: dos sitios que traducen `502` y dos logs `ERROR` distintos. Además esa dependencia necesita el `postal_code` ya validado, y engancharla al modelo `Query()` del RF-1 añade indirección sin ganar nada.
**Descartado (`WarehouseCacheRepository` construido dentro de la ruta a partir de `CacheRepository._redis`):** acceder a un atributo privado de otra clase; además rompe la posibilidad de `dependency_overrides` en los tests de `tests/api/`.
RF: **RF-2, RF-5**.

### D3 — Entrada negativa en una clave con prefijo propio (`postal-code-wh-unserved:`), leída junto a la positiva con un único `MGET`
**Elegido:** positiva en `postal-code-wh:{postal_code}` (el nombre que sugiere el propio RF-3) y negativa en `postal-code-wh-unserved:{postal_code}`. `WarehouseCacheRepository.get(postal_code)` hace **un** `MGET` de las dos claves (un solo viaje a Redis, igual que hoy la búsqueda hace un `GET`):
- positiva presente → `CachedWarehouse(warehouse="mad3")` (si coexistieran por una carrera, gana la positiva: se sirven datos en vez de un `404`);
- sólo negativa → `CachedWarehouse(warehouse=None)`;
- ninguna → `None` (miss).
Métodos de escritura: `set_served(postal_code, warehouse, ttl)` y `set_not_served(postal_code, ttl)`. Los valores llegan como `bytes`: `Redis.from_url` se crea sin `decode_responses` en `main.py`, y así se mantiene, porque `CacheRepository` depende de ello. Se decodifican con `.decode("utf-8")`.
**Descartado (misma clave con un valor centinela, p.ej. `postal-code-wh:{pc} = "__unserved__"` o `""`):** ahorra una clave, pero spec.md RF-11 pide literalmente "una **clave** distinguible de una resolución válida". Además, un centinela dentro del espacio de valores de un identificador que spec.md declara **opaco** ("no se asume ningún formato") es una colisión posible por construcción, aunque improbable. Con prefijos distintos es imposible.
**Descartado (dos `GET` secuenciales):** duplica la latencia de Redis en cada petición para resolver algo que `MGET` resuelve en un viaje.
RF: **RF-3, RF-4, RF-11**.

### D4 — Excepciones: `PostalCodeNotServedError` nueva (→ `404`); todo fallo de upstream reutiliza `UpstreamUnavailableError` (→ `502`)
**Elegido:**
- `app/exceptions.py` gana `PostalCodeNotServedError(Exception)`, excepción de dominio igual que `UpstreamUnavailableError`, sin tipos de httpx.
- `app/scrapers/mercadona_client.py` gana `WarehouseHeaderMissing(Exception)`, excepción propia de la capa scraper y hermana de `AlgoliaCredentialsUnavailable`, porque es un fallo de contrato del endpoint.
- En `resolve_warehouse` (servicio):
  - cliente devuelve `None` (`404`) o cache negativa vigente → `raise PostalCodeNotServedError`;
  - `httpx.TransportError`, o `HTTPStatusError` con `5xx`/`429` (tras agotar reintentos) → `UpstreamUnavailableError` (RF-8), igual que la traducción de `product_search.py:28-37`;
  - `WarehouseHeaderMissing` → `UpstreamUnavailableError` (RF-10), sin escribir cache;
  - `HTTPStatusError` con cualquier **otro** `4xx` (`400`, `403`…) → `UpstreamUnavailableError` (→ `502`). Ver la nota sobre este punto en §6.
- En `products.py`: `except PostalCodeNotServedError` → `HTTPException(404, detail="Postal code not served by Mercadona")`, sin reenviar el `error_msg` de Mercadona. El `except UpstreamUnavailableError` existente → `502` cubre ahora las dos llamadas (resolución y búsqueda). El decorador `@router.get` gana `404` en `responses=` para que Swagger lo documente (constitución #9).
**Descartado (una sola excepción `WarehouseResolutionError` con un campo `reason`):** obligaría a la ruta a inspeccionar el motivo para elegir entre `404` y `502`. Con dos tipos, cada uno se mapea a un código HTTP y el `except` lo expresa sin condicionales.
**Descartado (`resolve_warehouse` del cliente lanza `PostalCodeNotServedError` directamente):** el cliente tendría que conocer una excepción de dominio, y el servicio perdería el punto natural donde escribir la cache negativa antes de lanzar. Devolver `None` deja al cliente como traductor HTTP puro.
**Descartado (extraer ya un helper compartido para la traducción `httpx → UpstreamUnavailableError`):** serían dos puntos de uso (`product_search.py` y `warehouse_resolver.py`). Se acepta duplicar unas 6 líneas hasta que aparezca un tercero; extraerlo ahora obligaría a tocar los tests de errores de `product_search` en un spec que no trata de eso.
RF: **RF-8, RF-9, RF-10**.

### D5 — El `404` de `change-pc` ya no se reintenta hoy: `_request_with_retry` no se modifica, se añade un test de regresión
**Elegido:** no tocar `_request_with_retry` ni `_error_for_response`. Verificado en el código: `_error_for_response` (`mercadona_client.py`, rama `if response.status_code < 500: return None`) devuelve `None` para cualquier `4xx` distinto de `429`, y `_request_with_retry` devuelve esa respuesta **en el primer intento**, sin backoff ni `sleep` (D2 de plan.md 001: "no reintentar errores 4xx"; ya cubierto para `GET` por `test_does_not_retry_on_4xx`). Así, `resolve_warehouse` recibe el `404` tal cual y lo convierte en `None` antes de llamar a `raise_for_status()`. RF-9 exige "sin reintentar", y eso se garantiza con un test nuevo (`PUT` que responde `404` ⇒ `call_count == 1`, `asyncio.sleep` nunca llamado). No hace falta cambiar código.
Los reintentos de RF-8 salen gratis por la misma vía: `PUT` es idempotente (fijar el mismo código postal dos veces tiene el mismo efecto), así que reintentarlo con la política de spec 002 es seguro. `_request_with_retry` ya acepta `method="PUT"` y `json: dict[str, object]`.
**Descartado (una lista explícita de estados "no reintentables" que incluya `404`):** duplicaría una regla que ya existe de forma general (todo `4xx` menos `429`), y se abriría la puerta a que ambas diverjan.
RF: **RF-8, RF-9**; NFR "Reutiliza política anti-baneo existente".

### D6 — Redis caído: la degradación vive en `WarehouseCacheRepository`, con el mismo patrón que `CacheRepository`
**Elegido:** `get`/`set_served`/`set_not_served` capturan `RedisError`, loguean `WARNING` (`"Redis unavailable, skipping warehouse cache read for postal_code %s"`) y se comportan como miss / no-op, exactamente como `CacheRepository.get/set` hoy (D5 de plan.md 001). El servicio no sabe si Redis está caído: ve un miss, llama a `change-pc` y responde `200`/`404`/`502` según Mercadona. Con Redis caído, cada petición paga un `PUT` extra, como describe el caso límite de spec.md. Se acepta como degradación.
**Descartado (capturar `RedisError` dentro de `resolve_warehouse`):** duplica la política de resiliencia fuera del repositorio. El criterio de spec 001 es que la capa de persistencia absorbe sus propios fallos.
RF: caso límite "Redis no disponible para la resolución de almacén".

### D7 — Validación de 5 dígitos: `Field(pattern=r"^[0-9]{5}$")` en `ProductQuery` + la ruta recibe el modelo con `Annotated[ProductQuery, Query()]`
**Elegido:**
- `ProductQuery.postal_code: str = Field(pattern=r"^[0-9]{5}$")`.
- `get_products(query: Annotated[ProductQuery, Query()], ...)` en lugar de `postal_code: str, term: str` + `ProductQuery(...)` dentro del cuerpo. FastAPI (instalado: 0.141) valida los query params contra el modelo **antes** de ejecutar la ruta y responde `422` con su formato estándar, sin llegar a `resolve_warehouse` ni a Mercadona (RF-1). Swagger publica el `pattern` en el schema del parámetro.

Por qué hay que cambiar la firma de la ruta: hoy `ProductQuery(postal_code=..., term=...)` se construye **dentro** del cuerpo de `get_products` (`products.py:48`). Si sólo se añadiera el `pattern` al modelo, un `"1234"` lanzaría `pydantic.ValidationError` dentro de la ruta. FastAPI no la convierte en `422`, así que llegaría al `unhandled_exception_handler` de `main.py` y respondería **`500`**, lo que incumple RF-1.

Por qué `[0-9]` y no `\d`: el motor de regex de Pydantic v2 (Rust `regex`, Unicode por defecto) hace que `\d` acepte dígitos no ASCII (p.ej. `"٢٨٠٠١"`, dígitos arábigo-índicos). Esa cadena pasaría la validación y llegaría a Mercadona, contra el propósito de RF-1/H2. `[0-9]` es exacto.
**Descartado (`postal_code: Annotated[str, Query(pattern=...)]` en la firma y `ProductQuery` sin tocar):** funciona, pero el NFR "Validación Pydantic v2" dice textualmente que el formato se valida "en `ProductQuery`, no con checks manuales dispersos". La regla quedaría fuera del modelo, y cualquier otro consumidor futuro de `ProductQuery` no la heredaría.
**Descartado (`field_validator` a mano):** un `pattern` declarativo expresa lo mismo, se publica en OpenAPI y no necesita código.
RF: **RF-1**.

### D8 — Clave de búsqueda `search:{warehouse}:{term}`; las entradas antiguas `search:{postal_code}:{term}` caducan solas, sin limpieza
**Elegido:** en `product_search.py` cambia **una línea**: `cache_key = f"search:{warehouse}:{query.term}"`. `search_products` ya recibe `warehouse` como parámetro (D8 de plan.md 001), así que su firma no cambia. `SearchMeta.warehouse=warehouse` ya existe; RF-7 se cumple solo en cuanto la ruta pasa el almacén resuelto. `SearchMeta.postal_code` sigue siendo `query.postal_code`.

Cuando dos códigos postales del mismo almacén comparten entrada, el `SearchMeta` cacheado lleva el `postal_code` **del primero que la escribió**. Para no violar RF-7 ("`postal_code` seguirá reflejando el código postal recibido en la petición"), en un hit de cache el servicio devuelve `cached.model_copy(update={"search": cached.search.model_copy(update={"postal_code": query.postal_code})})`. Esto es un cambio pequeño pero **necesario**, y lo fija un test (ver §4, RF-6/RF-7).

**Entradas antiguas en Redis:** no se leen nunca más, porque ningún código construye ya `search:{postal_code}:...`. Caducan por su propia TTL (`CACHE_TTL_SECONDS`, 1h por defecto), así que como mucho 1h después del despliegue desaparecen solas. **No hace falta limpieza**. Colisión entre formato viejo y nuevo: sólo sería posible si un id de almacén fuera idéntico a un código postal de 5 dígitos. Los observados tienen 4 caracteres (`4701`, `mad3`), la ventana dura como mucho una TTL y el efecto sería servir un resultado ya incorrecto de antes del cambio. Se acepta. Si se quiere vaciar a mano tras desplegar: `redis-cli --scan --pattern 'search:*' | xargs redis-cli del` (opcional, no forma parte de la implementación).
**Descartado (versionar la clave, `search:v2:{warehouse}:{term}`):** elimina la colisión teórica, pero spec.md RF-6 fija el formato `search:{warehouse}:{term}`, y el problema que resolvería dura como mucho una TTL.
**Descartado (no reescribir `postal_code` en el hit):** es más simple, pero un cliente que pide `28002` recibiría `"postal_code": "28001"`, lo que incumple RF-7 y la compatibilidad de contrato.
RF: **RF-6, RF-7**.

### D9 — Logs de RF-12 en `warehouse_resolver.py`, junto a cada decisión; el `WARNING` de RF-10 en el cliente, donde se detecta
**Elegido** (mismo criterio que D6 de plan.md 003: el log vive junto a la lógica que decide):

| Evento | Nivel | Dónde | Mensaje (forma) |
|---|---|---|---|
| Cache hit positivo | `INFO` | servicio | `Warehouse cache hit postal_code=%s warehouse=%s` |
| Cache hit negativo | `INFO` | servicio | `Warehouse negative cache hit postal_code=%s (not served)` |
| Miss resuelto | `INFO` | servicio | `Resolved postal_code=%s to warehouse=%s via change-pc` |
| `404` de Mercadona | `WARNING` | servicio | `Postal code %s not served by Mercadona` |
| `2xx` sin `x-customer-wh` | `WARNING` | cliente | `change-pc returned %d without x-customer-wh for postal_code=%s` |
| Fallo de upstream | `ERROR` | ya existente: `_request_with_retry` ("Exhausted…") + `logger.exception` de la ruta | sin cambios |
| Redis caído | `WARNING` | repositorio (D6) | sin cabeceras ni valores de Redis |

Nunca se loguean cabeceras completas, cookies (`change-pc` puede devolver `Set-Cookie`) ni el cuerpo de la respuesta: sólo `postal_code`, el `warehouse` extraído y el status code. El `request_id` lo añade solo el `_RequestIdFilter` de spec 003. El mensaje del `logger.exception` de la ruta (`"Upstream unavailable for postal_code=%s term=%s"`) se mantiene, y ahora lee `query.postal_code`/`query.term`. `test_get_products_logs_error_when_upstream_unavailable` exige que haya **exactamente un** `ERROR`, así que el servicio no loguea `ERROR` por su cuenta al traducir a `UpstreamUnavailableError`.
**Descartado (un único log agregado en la ruta con el resultado de la resolución):** la ruta no sabe si fue hit o miss sin que el servicio le devuelva metadatos extra. Eso sería contrato interno nuevo sólo para loguear.
RF: **RF-10, RF-12**.

## 4. Estrategia de test

Todo con HTTP mockeado: respx en `tests/scrapers/` e integración, y `AsyncMock(spec=...)` en `tests/services/` y `tests/api/`, mismo estilo que specs 001-006. Redis con `fakeredis.FakeAsyncRedis()`, y `AsyncMock` con `side_effect=RedisConnectionError` para el caso caído (`test_cache_resilience.py`, `test_rf_edge_redis_down.py`). **Cero llamadas reales a Mercadona.** Cada bloque es un slice test-first (rojo → verde) que se convierte en tarea.

**RF-1 — `tests/models/test_query.py` + `tests/api/test_products.py`**
- `ProductQuery` acepta `"28001"`, `"01001"` (cero inicial conservado como texto) y `"51001"`.
- Rechaza (`ValidationError`) `"1234"`, `"123456"`, `"abcde"`, `"2800a"`, `" 28001"`, `""` y `"٢٨٠٠١"` (dígitos no ASCII, D7).
- API: `GET /api/v1/products?postal_code=1234&term=leche` → `422`; los mocks de `MercadonaClient` y del repositorio de almacén **no reciben ninguna llamada** (`assert_not_awaited`).

**RF-2 — `tests/scrapers/test_mercadona_client_warehouse.py` (nuevo, respx)**
- `PUT https://tienda.mercadona.es/api/postal-codes/actions/change-pc/` → `200` con `x-customer-wh: mad3` ⇒ devuelve `"mad3"`. Se afirma método `PUT` y cuerpo JSON exacto `{"new_postal_code": "28001"}` (`route.calls.last.request`).
- Ids opacos: `4701`, `3842` se devuelven tal cual (sin asumir formato).

**RF-3 / RF-4 / RF-11 — `tests/services/test_warehouse_cache.py` (nuevo, fakeredis)**
- `set_served("28001", "mad3", ttl=86400)` ⇒ `get("28001") == CachedWarehouse("mad3")`; la clave `postal-code-wh:28001` existe con `TTL` ≈ 86400 (`await redis.ttl(...)`).
- `set_not_served("99999", ttl=3600)` ⇒ `get("99999") == CachedWarehouse(None)`; la clave `postal-code-wh-unserved:99999` existe con `TTL` ≈ 3600, y la clave positiva **no** existe.
- Miss ⇒ `None`. Si coexisten ambas claves, gana la positiva.
- Redis caído (`AsyncMock`, `mget`/`set` lanzan `RedisConnectionError`) ⇒ `get` devuelve `None`, las escrituras no lanzan, y hay una línea `WARNING` en `caplog` (D6).

**RF-2 / RF-4 / RF-8 / RF-9 / RF-10 / RF-11 / RF-12 — `tests/services/test_warehouse_resolver.py` (nuevo, `AsyncMock`)**
- Miss + cliente devuelve `"mad3"` ⇒ devuelve `"mad3"`, llama a `set_served("28001", "mad3", ttl=settings.WAREHOUSE_CACHE_TTL_SECONDS)` y deja un log `INFO` con `28001` y `mad3`.
- Hit positivo ⇒ devuelve el almacén cacheado, `client.resolve_warehouse` **no** se llama (RF-4), log `INFO` de hit.
- Cliente devuelve `None` ⇒ `set_not_served(..., ttl=settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS)` y `PostalCodeNotServedError`.
- Hit negativo ⇒ `PostalCodeNotServedError` sin llamar al cliente (RF-11).
- Cliente lanza `httpx.TransportError`, `HTTPStatusError(503)`, `HTTPStatusError(429)` o `HTTPStatusError(403)` ⇒ `UpstreamUnavailableError` y **ninguna** escritura en cache.
- Cliente lanza `WarehouseHeaderMissing` ⇒ `UpstreamUnavailableError` y ninguna escritura en cache (RF-10).
- Logs (RF-12): ningún record contiene `Set-Cookie`, nombres de cabecera distintos de `x-customer-wh`, ni el `error_msg` de Mercadona.

**RF-8 / RF-9 / RF-10 en el cliente — `tests/scrapers/test_mercadona_client_warehouse.py`**
- `404` con `{"error_msg": "This zip code is outside of our working area"}` ⇒ devuelve `None`, `route.call_count == 1` y `asyncio.sleep` nunca llamado (espía con `monkeypatch`, mismo patrón que `test_mercadona_client_retry.py`). Esto fija D5.
- `503, 503, 200+cabecera` ⇒ recupera en el tercer intento (`call_count == 3`).
- `503` persistente ⇒ lanza `HTTPStatusError` tras `RETRY_MAX_ATTEMPTS`.
- `429` + `Retry-After: 0` ⇒ recupera.
- `200` sin `x-customer-wh` ⇒ `WarehouseHeaderMissing` + `WARNING` en `caplog` (RF-10).

**RF-5 / RF-8 / RF-9 / RF-10 en la API — `tests/api/test_products.py`, `tests/api/test_products_errors.py`**
- La ruta pasa el almacén resuelto a `client.search(term=..., warehouse="vlc1")` (se afirma el argumento).
- `PostalCodeNotServedError` ⇒ `404` con `detail == "Postal code not served by Mercadona"`, y el `error_msg` de Mercadona no aparece en el cuerpo.
- `UpstreamUnavailableError` durante la resolución ⇒ `502`, y `client.search` no se llama.

**RF-6 / RF-7 — `tests/services/test_product_search.py`**
- Actualizar `cache.get.assert_awaited_once_with("search:28001:leche")` → `"search:mad1:leche"` (la clave pasa a depender del almacén).
- Nuevo: hit de cache escrito por `28001` y leído por `28002` con el mismo almacén ⇒ la respuesta lleva `search.postal_code == "28002"` y `search.warehouse == "mad3"` (D8).

**Integración — `tests/integration/test_warehouse_resolution.py` (nuevo; app real + lifespan + fakeredis + respx)**
- `28001`→`mad3` y `46001`→`vlc1` (dos rutas `change-pc` distinguidas por el cuerpo JSON, o `side_effect` por request) ⇒ `SearchMeta.warehouse` distinto, y Algolia recibe `indexName` `products_prod_mad3_es` y `products_prod_vlc1_es` respectivamente (H1, RF-5, RF-6).
- Dos códigos postales que resuelven al mismo almacén con el mismo `term` ⇒ Algolia `call_count == 1` (H4), y cada respuesta lleva su propio `postal_code` (RF-7).
- Misma petición dos veces ⇒ `change-pc` `call_count == 1` (RF-4; criterio de finalización de spec.md).
- `99999` → `404` dos veces ⇒ ambas respuestas `404` y `change-pc` `call_count == 1` (RF-11).
- `change-pc` `503` persistente ⇒ `502` (RF-8).
- `200` sin cabecera ⇒ `502`, y una segunda petición vuelve a llamar a `change-pc` porque no quedó nada cacheado (RF-10).
- Redis caído (fixture `client_with_broken_redis` de `test_rf_edge_redis_down.py`) ⇒ `200` y `change-pc` llamado en cada petición.

**Regresión de specs 001-006 (cambios obligatorios en tests existentes)**
- `tests/integration/*` que golpean `/api/v1/products` (11 archivos: `test_rf1..rf5`, `test_rf_edge_*`, `test_auth_happy_path`, `test_credential_caching`, `test_request_id_correlation`) usan `respx_mock` con rutas explícitas. Una petición `PUT change-pc` no mockeada haría fallar el test. Se añade un helper `mock_change_pc(respx_mock, warehouse="mad1")` en `tests/integration/conftest.py`, **no autouse**: el `respx_mock` con `assert_all_called` rompería `test_smoke.py` y `test_auth_short_circuit.py`, que no llaman a Mercadona. Se invoca en cada test afectado. Con `warehouse="mad1"`, las aserciones `body["search"]["warehouse"] == "mad1"` existentes (`test_rf1_happy_path.py:54`, `test_auth_happy_path.py:29`) siguen siendo válidas sin cambiarlas.
- `test_rf3_retry.py`, `test_rf5_rate_limit.py`: su `503`/`429` persistente se aplica al manifest y **no** a `change-pc`, que debe responder `200` para que el test siga ejerciendo lo que ejercía.
- `test_auth_short_circuit.py`: añadir la aserción de que `change-pc` no se llama sin `X-API-Key`.
- `tests/api/test_products*.py` y los dos tests de `tests/test_main.py` con `dependency_overrides`: añadir un override de `get_warehouse_cache_repository` (`AsyncMock(spec=WarehouseCacheRepository)` con `get.return_value = None`) y `client.resolve_warehouse.return_value = "mad1"`. Sin eso, `AsyncMock(spec=MercadonaClient).resolve_warehouse` devuelve un `AsyncMock` en vez de un `str`, y `SearchMeta` falla al validar.
- `tests/core/test_dependencies.py`: el `_make_request` gana el campo `warehouse_cache_repository`, y se añade un test para el nuevo provider. `tests/core/test_config.py`: defaults `86400`/`3600` y override por variable de entorno. `tests/test_main.py::test_lifespan_populates_app_state`: afirmar `app.state.warehouse_cache_repository`.

**Cobertura:** mismo objetivo ≥80% del código nuevo/modificado (specs 001-006 alcanzaron 99% real), medida con `pytest --cov=app`.

## 5. Secuencia de implementación (base de tasks.md)

Cada paso: test rojo → código mínimo → verde → `ruff check . && ruff format .`. Los pasos 1-5 son aditivos (nada los consume aún, la suite existente sigue verde). El paso 6 es el único que cambia el comportamiento de la ruta, y **debe** incluir en el mismo commit la actualización de los tests existentes.

1. **Settings** — `WAREHOUSE_CACHE_TTL_SECONDS`/`WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS` + tests en `test_config.py` (RF-3, RF-11).
2. **Excepciones** — `PostalCodeNotServedError` en `app/exceptions.py`; `WarehouseHeaderMissing` en `mercadona_client.py` (D4).
3. **Cliente** — `MercadonaClient.resolve_warehouse` + `test_mercadona_client_warehouse.py`: `200`, `404` sin reintento, `5xx` con reintento, `429`, `2xx` sin cabecera (RF-2, RF-8, RF-9, RF-10; D5).
4. **Repositorio** — `CachedWarehouse` + `WarehouseCacheRepository` en `cache.py` + `test_warehouse_cache.py`, incluido Redis caído (RF-3, RF-4, RF-11; D3, D6).
5. **Servicio** — `app/services/warehouse_resolver.py` + `test_warehouse_resolver.py`, con logs (RF-2..RF-4, RF-8..RF-12; D4, D9).
6. **Cableado + validación + clave de búsqueda** (commit atómico):
   a. `ProductQuery` con `pattern` + tests de modelo (RF-1; D7).
   b. `AppState` + `get_warehouse_cache_repository` + `lifespan` + tests de `test_dependencies.py`/`test_main.py`.
   c. `products.py`: `Annotated[ProductQuery, Query()]`, borrar `_DEFAULT_WAREHOUSE`, llamar a `resolve_warehouse`, mapear `404`/`502`, `responses=` actualizado (RF-1, RF-5, RF-8, RF-9, RF-10; D2, D4).
   d. `product_search.py`: clave `search:{warehouse}:{term}` + reescritura de `postal_code` en el hit (RF-6, RF-7; D8).
   e. Actualizar los tests existentes de `tests/api/`, `tests/test_main.py`, `tests/services/test_product_search.py` y `tests/integration/*` (helper `mock_change_pc`).
7. **Integración nueva** — `tests/integration/test_warehouse_resolution.py` (H1, H4, RF-4, RF-8, RF-10, RF-11, Redis caído).
8. **Docs vivas** — `README.md` (variables, limitación de `mad1` eliminada, ejemplo de respuesta con `mad3`) y `.env.example`. Comprobar que `/docs` muestra el `pattern` de `postal_code` y la respuesta `404`.
9. **Verificación final** — suite completa, cobertura, `ruff`, y la verificación manual de spec.md (`28001`→`mad3`, `46001`→`vlc1`, `"1234"`/`"abcde"`→`422`).

## 6. Riesgos y notas

- **`4xx` distintos de `404` en `change-pc` (hueco de spec.md, decisión de este plan):** spec.md sólo define `404` (RF-9) y `5xx`/`429`/transporte (RF-8). Un `400`/`403` (p.ej. bloqueo del WAF) con la traducción actual de `product_search.py` se re-lanzaría y acabaría en `500` vía el handler global. Este plan lo mapea a `502` (D4), porque para un código postal ya validado a 5 dígitos es un fallo del upstream y no un bug nuestro, y **no** lo cachea. **Confirmado por el usuario (2026-09-24): `502`.** Recogido en spec.md como RF-13.
- **Cookie jar compartido:** el `httpx.AsyncClient` del `lifespan` es único por proceso y guarda las cookies que devuelva `change-pc` (Mercadona fija la sesión del código postal). Peticiones concurrentes de distintos códigos postales las sobrescriben entre sí. Hoy es inocuo: el almacén se lee de la cabecera **de cada respuesta** y Algolia está en otro dominio, así que no recibe esas cookies. Si en el futuro Mercadona hiciera depender `x-customer-wh` de una cookie previa, el síntoma serían almacenes cruzados bajo concurrencia. No se mitiga ahora (no hay evidencia); se deja anotado.
- **Latencia añadida en frío:** un miss de almacén añade un `PUT` (con reintentos, en el peor caso el mismo presupuesto que spec 002) antes de Algolia. Con TTL de 24h se paga una vez por código postal y día. El NFR de p95 sin cache de spec 001 (<1200ms) puede verse presionado en la primera petición de cada código postal. Medirlo en la verificación manual.
- **Enumeración de códigos postales:** fuera de alcance según spec.md. La cache negativa sólo protege de repeticiones del mismo código.
- **Reescritura de `postal_code` en el hit de búsqueda (D8):** es el único cambio de comportamiento en `search_products` más allá de la clave. Si se omitiera, RF-7 fallaría de forma silenciosa sólo cuando dos códigos postales comparten almacén, un caso que la suite actual no ejerce. Por eso tiene test propio.
- **Superficie de cambio en tests existentes:** alrededor de 17 archivos de test cambian (sobre todo mocks de `change-pc`). Es mecánico, pero es donde más fácil es romper la suite de specs 001-006. El paso 6 debe cerrarse con la suite completa en verde, no sólo con los tests nuevos.

## 7. Estimación de líneas cambiadas

| Bloque | Líneas (≈) |
|---|---|
| Código de producción (`config`, `query`, `exceptions`, `mercadona_client`, `cache`, `warehouse_resolver` nuevo, `product_search`, `products`, `dependencies`, `state`, `main`) | 190 |
| Tests nuevos (`test_mercadona_client_warehouse`, `test_warehouse_cache`, `test_warehouse_resolver`, `test_warehouse_resolution`, casos nuevos en `test_query`/`test_products*`/`test_product_search`/`test_config`/`test_dependencies`) | 620 |
| Tests existentes actualizados (helper `mock_change_pc` + 11 integraciones + overrides en `tests/api/` y `test_main.py`) | 90 |
| Docs (`README.md`, `.env.example`) | 20 |
| **Total** | **≈ 920** |

**Supera el presupuesto de 400 líneas por PR.** Propuesta de PRs encadenados que siguen la secuencia de §5 (cada uno deja la suite en verde):
- **PR 1** (pasos 1-3, ≈ 260): settings + excepciones + `MercadonaClient.resolve_warehouse` con sus tests. Aditivo.
- **PR 2** (pasos 4-5, ≈ 330): `WarehouseCacheRepository` + `warehouse_resolver.py` con sus tests. Aditivo.
- **PR 3** (pasos 6-9, ≈ 330): cableado, validación, clave de búsqueda, actualización de tests existentes, integración nueva y docs. Es el único que cambia el comportamiento observable, y no puede partirse más sin dejar la suite en rojo entre commits.
**Decisión (usuario, 2026-09-24): PRs encadenados (PR 1 → PR 2 → PR 3).** Se descarta el PR único con `size:exception`. `tasks.md` debe agrupar las tareas según estos tres PRs.
