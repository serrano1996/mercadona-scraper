# Tasks 007 — Warehouse Resolution

Desglose de [plan.md](plan.md). Orden = orden de dependencia (§5 de plan.md). Cada tarea <30 min y es una unidad de trabajo revisable: TDD estricto activo — cada tarea de comportamiento primero escribe el test en rojo (RED), luego el código mínimo para ponerlo en verde (GREEN), y sólo entonces refactoriza si hace falta, dejando `pytest -q` completo en verde al cerrar la tarea. Entrega en 3 PRs encadenados (decisión del usuario, 2026-09-24, ver plan.md §7): PR1 → PR2 → PR3, cada uno basado en el anterior.

## PR 1 — Settings, excepciones y `MercadonaClient.resolve_warehouse`

Rama `007-warehouse-resolution-pr1`, base `main`. Aditivo puro: nada consume aún el código nuevo, la suite existente sigue en verde sin tocar ningún test preexistente. Estimación: **≈260 líneas** (plan.md §7, pasos 1-3 de §5).

- [x] **T1 — `core/config.py`: nuevas TTL de almacén**
  `WAREHOUSE_CACHE_TTL_SECONDS: int = 86400` y `WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS: int = 3600` en `Settings`, mismo patrón que `CACHE_TTL_SECONDS`.
  RED: `tests/core/test_config.py` — `Settings().WAREHOUSE_CACHE_TTL_SECONDS == 86400` y `Settings().WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS == 3600` por defecto; override vía variable de entorno para ambas.
  GREEN: añade los dos campos a `Settings`.
  Depende: —.
  RF: RF-3, RF-11.
  Hecho cuando: los tests nuevos están en verde, `pytest -q` completo sigue en verde y no se ha tocado ningún test existente.

- [x] **T2 — `app/exceptions.py` y `mercadona_client.py`: excepciones de dominio nuevas**
  `PostalCodeNotServedError(Exception)` en `app/exceptions.py` (hermana de `UpstreamUnavailableError`, sin tipos de httpx). `WarehouseHeaderMissing(Exception)` en `app/scrapers/mercadona_client.py` (hermana de `AlgoliaCredentialsUnavailable`, D4 de plan.md).
  RED: test unitario mínimo — ambas excepciones son instanciables, heredan de `Exception` y no llevan atributos obligatorios.
  GREEN: define las dos clases, sin lógica adicional.
  Depende: —.
  RF: soporte de RF-8, RF-9, RF-10 (D4).
  Hecho cuando: los tests están en verde y `pytest -q` completo sigue en verde.

- [x] **T3 — `MercadonaClient.resolve_warehouse`: camino feliz**
  Nuevo método `async def resolve_warehouse(self, postal_code: str) -> str | None`, capa `scrapers/` (D1 de plan.md): `PUT {MERCADONA_BASE_URL}/api/postal-codes/actions/change-pc/` con `json={"new_postal_code": postal_code}` a través de `_request_with_retry` (reutiliza la política anti-baneo de spec 002, sin lógica de reintento paralela); en `2xx` con cabecera `x-customer-wh` devuelve su valor tal cual, sin asumir formato (ids opacos como `4701`, `3842`).
  RED: `tests/scrapers/test_mercadona_client_warehouse.py` (nuevo, respx) — `200` con `x-customer-wh: mad3` ⇒ devuelve `"mad3"`; se afirma método `PUT` y cuerpo JSON exacto `{"new_postal_code": "28001"}` (`route.calls.last.request`); ids opacos de 4 caracteres (`4701`, `3842`) se devuelven sin transformación.
  GREEN: implementa `resolve_warehouse` en `mercadona_client.py`.
  Depende: T2.
  RF: RF-2.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T4 — `MercadonaClient.resolve_warehouse`: errores y regresión de no-reintento en `404`**
  Extiende `resolve_warehouse`: `404` ⇒ devuelve `None` (RF-9); `2xx` sin `x-customer-wh` ⇒ `raise WarehouseHeaderMissing` + `logger.warning(...)` sin loguear cabeceras completas ni el cuerpo (RF-10, RF-12); `5xx`/`429`/transporte ⇒ se reintenta vía `_request_with_retry` igual que hoy (RF-8), sin tocar `_error_for_response` ni `_request_with_retry` (D5 de plan.md: el `404` ya no se reintenta porque `_error_for_response` devuelve `None` para cualquier `4xx` distinto de `429` en el primer intento).
  RED (en `tests/scrapers/test_mercadona_client_warehouse.py`): `404` con `{"error_msg": "This zip code is outside of our working area"}` ⇒ devuelve `None`, **`route.call_count == 1`** y `asyncio.sleep` nunca invocado (espía con `monkeypatch`, mismo patrón que `test_mercadona_client_retry.py`) — **regresión explícita de D5, sin reintento en `404`**; `503, 503, 200+cabecera` ⇒ recupera en el tercer intento (`call_count == 3`); `503` persistente ⇒ lanza `HTTPStatusError` tras `RETRY_MAX_ATTEMPTS`; `429` + `Retry-After: 0` ⇒ recupera; `200` sin `x-customer-wh` ⇒ `WarehouseHeaderMissing` + una línea `WARNING` en `caplog` sin `Set-Cookie` ni otras cabeceras; `403` (y `400`) ⇒ se propaga como error de estado HTTP con **`route.call_count == 1`** y `asyncio.sleep` nunca invocado — regresión de no-reintento de RF-13 (el mapeo a `502` se prueba en T6).
  GREEN: código mínimo para que todos los casos anteriores pasen (probablemente ya cubierto por T3 + el comportamiento existente de `_request_with_retry`; esta tarea confirma y fija el contrato con tests).
  Depende: T3.
  RF: RF-8, RF-9, RF-10, RF-13.
  Hecho cuando: los tests nuevos (incluida la regresión de `404` sin reintento) están en verde, `pytest -q` completo sigue en verde y `ruff check . && ruff format .` no reportan errores sobre los archivos tocados en PR1.

## PR 2 — `WarehouseCacheRepository` y `app/services/warehouse_resolver.py`

Rama `007-warehouse-resolution-pr2`, base `007-warehouse-resolution-pr1`. Aditivo puro: sigue sin haber ningún consumidor en la ruta, la suite existente permanece intacta. Estimación: **≈330 líneas** (plan.md §7, pasos 4-5 de §5).

- [x] **T5 — `cache.py`: `CachedWarehouse` + `WarehouseCacheRepository`**
  `CachedWarehouse` (dataclass `frozen`, `warehouse: str | None`). `WarehouseCacheRepository` con `get(postal_code) -> CachedWarehouse | None` (un único `MGET` sobre `postal-code-wh:{postal_code}` y `postal-code-wh-unserved:{postal_code}`; gana la positiva si coexisten), `set_served(postal_code, warehouse, ttl)` y `set_not_served(postal_code, ttl)` (D3 de plan.md). Degradación ante `RedisError`: `get`/`set_served`/`set_not_served` capturan el error, loguean `WARNING` (sin cabeceras ni valores de Redis) y se comportan como miss/no-op, igual que `CacheRepository` (D6).
  RED: `tests/services/test_warehouse_cache.py` (nuevo, fakeredis) — `set_served("28001", "mad3", ttl=86400)` ⇒ `get("28001") == CachedWarehouse("mad3")`, clave `postal-code-wh:28001` con `TTL` ≈ 86400; `set_not_served("99999", ttl=3600)` ⇒ `get("99999") == CachedWarehouse(None)`, clave `postal-code-wh-unserved:99999` con `TTL` ≈ 3600 y la clave positiva ausente; miss ⇒ `None`; coexistencia de ambas claves ⇒ gana la positiva; Redis caído (`AsyncMock` con `side_effect=RedisConnectionError` en `mget`/`set`) ⇒ `get` devuelve `None`, las escrituras no lanzan y hay una línea `WARNING` en `caplog`.
  GREEN: implementa `CachedWarehouse` y `WarehouseCacheRepository` en `app/services/cache.py`, junto a `CacheRepository`.
  Depende: T1.
  RF: RF-3, RF-4, RF-11.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T6 — `app/services/warehouse_resolver.py`: función `resolve_warehouse`**
  Nuevo módulo, `resolve_warehouse(postal_code, cache, client, settings) -> str` (D1): consulta `cache.get`; si hay hit positivo devuelve el almacén sin llamar al cliente (RF-4) y loguea `INFO` de hit; si hay hit negativo lanza `PostalCodeNotServedError` sin llamar al cliente (RF-11) y loguea `INFO`; en miss llama a `client.resolve_warehouse`: `str` ⇒ `cache.set_served(..., ttl=settings.WAREHOUSE_CACHE_TTL_SECONDS)`, devuelve el valor y loguea `INFO` de resolución; `None` ⇒ `cache.set_not_served(..., ttl=settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS)` y `raise PostalCodeNotServedError`, con `WARNING`; `httpx.TransportError` o `HTTPStatusError` (`5xx`, `429`, o cualquier otro `4xx` como `400`/`403`, tras agotar reintentos) ⇒ `raise UpstreamUnavailableError` sin escribir cache (RF-8, RF-13); `WarehouseHeaderMissing` ⇒ `raise UpstreamUnavailableError` sin escribir cache (RF-10). Logs siguiendo D9 de plan.md: nunca cabeceras completas, cookies ni `error_msg` de Mercadona — sólo `postal_code`, `warehouse` y status code.
  RED: `tests/services/test_warehouse_resolver.py` (nuevo, `AsyncMock`) — miss + cliente devuelve `"mad3"` ⇒ devuelve `"mad3"`, llama a `set_served("28001", "mad3", ttl=settings.WAREHOUSE_CACHE_TTL_SECONDS)`, log `INFO`; hit positivo ⇒ devuelve el almacén cacheado, `client.resolve_warehouse` no se llama, log `INFO`; cliente devuelve `None` ⇒ `set_not_served(..., ttl=settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS)` y `PostalCodeNotServedError`; hit negativo ⇒ `PostalCodeNotServedError` sin llamar al cliente; cliente lanza `httpx.TransportError`, `HTTPStatusError(503)`, `HTTPStatusError(429)` o `HTTPStatusError(403)` ⇒ `UpstreamUnavailableError` y ninguna escritura en cache; cliente lanza `WarehouseHeaderMissing` ⇒ `UpstreamUnavailableError` sin escritura en cache; ningún record de `caplog` contiene `Set-Cookie`, cabeceras distintas de `x-customer-wh`, ni el `error_msg` de Mercadona.
  GREEN: implementa `resolve_warehouse` en `app/services/warehouse_resolver.py`.
  Depende: T2, T4, T5.
  RF: RF-2, RF-3, RF-4, RF-5, RF-8, RF-9, RF-10, RF-11, RF-12, RF-13.
  Hecho cuando: los tests nuevos están en verde, `pytest -q` completo sigue en verde y `ruff check . && ruff format .` no reportan errores sobre los archivos tocados en PR2.

## PR 3 — Cableado de la ruta, validación, clave de cache y regresión

Rama `007-warehouse-resolution-pr3`, base `007-warehouse-resolution-pr2`. Único PR que cambia comportamiento observable — no puede partirse más sin dejar la suite en rojo entre commits (plan.md §7). Estimación: **≈330 líneas** (plan.md §7, pasos 6-9 de §5).

- [x] **T7 — `models/query.py`: validación de 5 dígitos**
  `ProductQuery.postal_code: str = Field(pattern=r"^[0-9]{5}$")` (D7 de plan.md — `[0-9]` y no `\d`, porque `\d` en el motor Rust de Pydantic v2 acepta dígitos Unicode no ASCII).
  RED: `tests/models/test_query.py` — acepta `"28001"`, `"01001"` (cero inicial conservado) y `"51001"`; rechaza (`ValidationError`) `"1234"`, `"123456"`, `"abcde"`, `"2800a"`, `" 28001"`, `""` y `"٢٨٠٠١"` (dígitos arábigo-índicos).
  GREEN: añade el `pattern` al campo.
  Depende: T6.
  RF: RF-1.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T8 — `core/state.py` + `core/dependencies.py` + `main.py`: cableado de `WarehouseCacheRepository`**
  `AppState` gana `warehouse_cache_repository: WarehouseCacheRepository`; `dependencies.py` añade `get_warehouse_cache_repository(request)` (mismo patrón que `get_cache_repository`, D2 de plan.md); `main.py` en el `lifespan` crea `WarehouseCacheRepository(redis_client)` sobre el mismo `redis_client` que `CacheRepository` y lo asigna a `app.state.warehouse_cache_repository`.
  RED: `tests/core/test_dependencies.py` — `_make_request` gana el campo `warehouse_cache_repository`, test nuevo para `get_warehouse_cache_repository` (mismo criterio `is` que el resto de providers); `tests/test_main.py::test_lifespan_populates_app_state` — afirma `app.state.warehouse_cache_repository`.
  GREEN: implementa los tres cambios.
  Depende: T7.
  RF: soporte de RF-2, RF-5 (D2).
  Hecho cuando: los tests nuevos y actualizados están en verde y `pytest -q` completo sigue en verde.

- [x] **T9 — `api/v1/products.py`: resolución de almacén y mapeo de errores**
  Firma `get_products(query: Annotated[ProductQuery, Query()], ...)` (D7 — FastAPI valida antes de ejecutar la ruta, evitando el `500` que daría un `ValidationError` interno); borra `_DEFAULT_WAREHOUSE`; declara `WarehouseCacheDep = Annotated[WarehouseCacheRepository, Depends(get_warehouse_cache_repository)]` reexportado en `__all__`; dentro de `get_products`, en el mismo bloque `try`: `warehouse = await resolve_warehouse(query.postal_code, cache, client, settings)` y luego `search_products(query, warehouse=warehouse, ...)`; `except PostalCodeNotServedError` ⇒ `HTTPException(404, detail="Postal code not served by Mercadona")` sin reenviar el `error_msg` de Mercadona; el `except UpstreamUnavailableError` existente cubre ahora ambas llamadas ⇒ `502`; `responses=` del decorador `@router.get` gana `404` (constitución #9).
  RED: `tests/api/test_products.py` — la ruta pasa el almacén resuelto a `client.search(term=..., warehouse="vlc1")` (se afirma el argumento); `GET /api/v1/products?postal_code=1234&term=leche` ⇒ `422`, y los mocks de `MercadonaClient`/`WarehouseCacheRepository` no reciben ninguna llamada (`assert_not_awaited`). `tests/api/test_products_errors.py` — `PostalCodeNotServedError` durante la resolución ⇒ `404` con `detail == "Postal code not served by Mercadona"`, sin el `error_msg` de Mercadona en el cuerpo; `UpstreamUnavailableError` durante la resolución ⇒ `502`, y `client.search` no se llama.
  GREEN: implementa el cableado descrito.
  Depende: T8.
  RF: RF-1, RF-5, RF-8, RF-9, RF-10.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [ ] **T10 — `services/product_search.py`: clave de cache por almacén**
  `cache_key = f"search:{warehouse}:{query.term}"` (antes `search:{postal_code}:{term}`, D8 de plan.md); en un hit de cache, reescribe `SearchMeta.postal_code` con el código postal de la petición actual: `cached.model_copy(update={"search": cached.search.model_copy(update={"postal_code": query.postal_code})})`, para no violar RF-7 cuando dos códigos postales comparten almacén.
  RED: `tests/services/test_product_search.py` — actualiza `cache.get.assert_awaited_once_with("search:28001:leche")` → `"search:mad1:leche"`; test nuevo: hit de cache escrito por `28001` y leído por `28002` (mismo almacén) ⇒ la respuesta lleva `search.postal_code == "28002"` y `search.warehouse == "mad3"`.
  GREEN: aplica el cambio de clave y la reescritura en el hit.
  Depende: T9.
  RF: RF-6, RF-7.
  Hecho cuando: los tests están en verde y `pytest -q` completo sigue en verde.

- [ ] **T11 — Regresión: actualiza la suite existente (specs 001-006) para `change-pc`**
  Añade `mock_change_pc(respx_mock, warehouse="mad1")` (no autouse) en `tests/integration/conftest.py`; invócalo en los 11 archivos de integración afectados (`test_rf1..rf5`, `test_rf_edge_*`, `test_auth_happy_path`, `test_credential_caching`, `test_request_id_correlation`) que golpean `/api/v1/products`; en `test_rf3_retry.py`/`test_rf5_rate_limit.py` el `503`/`429` persistente se aplica sólo al manifest, `change-pc` responde `200`; en `test_auth_short_circuit.py` añade la aserción de que `change-pc` no se llama sin `X-API-Key`; en `tests/api/test_products*.py` y los dos tests de `tests/test_main.py` con `dependency_overrides`, añade el override de `get_warehouse_cache_repository` (`AsyncMock(spec=WarehouseCacheRepository)` con `get.return_value = None`) y `client.resolve_warehouse.return_value = "mad1"`.
  RED/GREEN: no aplica TDD clásico (no hay comportamiento nuevo que probar) — es la actualización mecánica de mocks que la suite existente necesita para no fallar tras T9/T10; cada archivo tocado se ejecuta tras el cambio para confirmar que vuelve a estar en verde.
  Depende: T10.
  RF: regresión — mantiene en verde specs 001-006 tras activar RF-2, RF-5, RF-6.
  Hecho cuando: `pytest -q` completo está en verde, incluidas todas las suites de specs 001-006 sin xfail ni skip nuevos.

- [ ] **T12 — Integración nueva: `tests/integration/test_warehouse_resolution.py`**
  App real + `lifespan` + fakeredis + respx, cero llamadas reales a Mercadona.
  RED: `28001`→`mad3` y `46001`→`vlc1` (dos rutas `change-pc` distinguidas por el cuerpo JSON o `side_effect` por request) ⇒ `SearchMeta.warehouse` distinto, y Algolia recibe `indexName` `products_prod_mad3_es`/`products_prod_vlc1_es` (H1, RF-5, RF-6); dos códigos postales que resuelven al mismo almacén con el mismo `term` ⇒ Algolia `call_count == 1` (H4) y cada respuesta lleva su propio `postal_code` (RF-7); misma petición dos veces ⇒ `change-pc` `call_count == 1` (RF-4); `99999` → `404` dos veces ⇒ ambas respuestas `404` y `change-pc` `call_count == 1` (RF-11); `change-pc` `503` persistente ⇒ `502` (RF-8); `200` sin cabecera ⇒ `502`, y una segunda petición vuelve a llamar a `change-pc` porque no quedó nada cacheado (RF-10); Redis caído (fixture `client_with_broken_redis` de `test_rf_edge_redis_down.py`) ⇒ `200` y `change-pc` llamado en cada petición.
  GREEN: si algún caso falla, ajusta el cableado de T8-T10 (no debería hacer falta código nuevo si T1-T11 están completas).
  Depende: T11.
  RF: RF-4, RF-6, RF-7, RF-8, RF-10, RF-11; H1, H4.
  Hecho cuando: todos los casos anteriores están en verde en un único archivo de test y `pytest -q` completo sigue en verde.

- [ ] **T13 — Docs vivas: `README.md` y `.env.example`**
  `README.md`: añade `WAREHOUSE_CACHE_TTL_SECONDS`/`WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS` a la tabla de variables, borra la limitación "Resolución de almacén provisional" (cierra D8 de plan.md 001) y actualiza el ejemplo de respuesta con un almacén real (p.ej. `mad3`). `.env.example`: añade las dos variables nuevas con sus valores por defecto.
  Depende: T12.
  RF: constitución #9/#10 (docs vivas).
  Hecho cuando: `README.md` no menciona ya `mad1` como almacén fijo, y `.env.example` contiene las dos variables nuevas con `86400`/`3600`.

- [ ] **T14 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que specs 001-006, criterio de finalización de spec.md).
  Depende: T1–T13.
  RF: criterio de finalización de spec.md; constitución #7, #8.
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80% sobre el código nuevo/modificado.

- [ ] **T15 — Verificación final**
  Con la suite completa mockeada (fakeredis + respx, **nunca contra la API real de Mercadona**): `pytest -q` completo en verde (specs 001-007); levantar la app y confirmar que `/docs` muestra el `pattern` de `postal_code` en el schema del parámetro y la respuesta `404` documentada en `responses=`. Verificación manual de spec.md, con `change-pc` mockeado: `28001`→`mad3` y `46001`→`vlc1` devuelven `SearchMeta.warehouse` distinto y catálogo/precio distinto; `postal_code="1234"` ⇒ `422`; repetir la misma petición dentro de `WAREHOUSE_CACHE_TTL_SECONDS` no repite la llamada `change-pc` (verificado por `call_count` sobre el mock).
  Depende: T14.
  RF: criterio de finalización de spec.md (manual + suite completa + cobertura + lint).
  Hecho cuando: los tres checks manuales (warehouses distintos, `422`, `call_count` sin repetir `change-pc`) y la carga de `/docs` se confirman, todo con mocks, sin ninguna llamada real a Mercadona.

## Trazabilidad RF → tareas

| RF | Descripción (resumen) | Tareas |
|---|---|---|
| RF-1 | `postal_code` inválido (≠5 dígitos) ⇒ `422` sin llamar a Mercadona | T7, T9 |
| RF-2 | Resolución de almacén vía `change-pc` + `x-customer-wh` | T3, T6, T8, T9, T12 |
| RF-3 | Cache Redis de `postal_code -> warehouse` con TTL configurable | T1, T5, T6 |
| RF-4 | Reutiliza resolución cacheada vigente, sin repetir `change-pc` | T5, T6, T12, T15 |
| RF-5 | Almacén resuelto sustituye a `_DEFAULT_WAREHOUSE` en `search()`/`search_products` | T6, T8, T9, T12 |
| RF-6 | Clave de cache de búsqueda `search:{warehouse}:{term}` | T10, T12 |
| RF-7 | `SearchMeta.warehouse` real; `SearchMeta.postal_code` refleja la petición | T10, T12 |
| RF-8 | `5xx`/`429`/transporte tras reintentos ⇒ `502` | T4, T6, T9, T12 |
| RF-9 | `404` de `change-pc` ⇒ `404` propio, sin reintento (D5) | T4, T6, T9, T12 |
| RF-10 | `2xx` sin `x-customer-wh` ⇒ `502` + `WARNING`, sin cachear | T4, T6, T9, T12 |
| RF-11 | Cache negativa de "sin servicio" con TTL corta configurable | T1, T5, T6, T12 |
| RF-12 | Logs `INFO`/`WARNING` de cada resolución, sin cabeceras/cuerpos completos | T4, T6 |
| RF-13 | `4xx` distinto de `404`/`429` en `change-pc` ⇒ `502`, sin reintento ni cache | T4, T6 |

Todos los RF-1 a RF-13 quedan cubiertos por al menos una tarea; ninguno queda sin mapear.
