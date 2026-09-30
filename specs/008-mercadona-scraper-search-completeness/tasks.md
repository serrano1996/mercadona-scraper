# Tasks 008 — Search Completeness

Desglose de [plan.md](plan.md). Orden = orden de dependencia (§5 de plan.md). Cada tarea <30 min y es una unidad de trabajo revisable: TDD estricto activo — cada tarea de comportamiento primero escribe el test en rojo (RED), luego el código mínimo para ponerlo en verde (GREEN), y sólo entonces refactoriza si hace falta, dejando `pytest -q` completo en verde al cerrar la tarea. **Ninguna tarea deja la suite en rojo** (plan.md §7). Entrega en 2 PRs encadenados (decisión del usuario, 2026-09-30): PR1 → PR2.

Requisito previo: spec 007 fusionada (la ruta recibe `Annotated[ProductQuery, Query()]` y la clave de cache es por almacén).

## PR 1 — Validación y normalización del término

Rama `008-search-completeness-pr1`, base `main` con la spec 007 fusionada. Cambia comportamiento observable sólo en los términos inválidos (`422`) y en el valor de `SearchMeta.term` (normalizado). Estimación: **≈110 líneas** (plan.md §7, pasos 1-3 de §5).

- [x] **T1 — `models/query.py`: `term` normalizado y con límites**
  `term: str = Field(min_length=1, max_length=100)` + `field_validator("term", mode="before")` que devuelve `" ".join(value.split()).lower()` (D1 de plan.md), de forma que `min_length`/`max_length` se evalúan sobre el valor ya normalizado.
  RED: `tests/models/test_query.py` — normaliza `"Leche"` → `"leche"`, `"  leche  "` → `"leche"`, `"leche   entera"` → `"leche entera"`, `"\tLeche\n"` → `"leche"`; rechaza (`ValidationError`) `""`, `"   "` y un término de 101 caracteres; acepta uno de 100 y uno de 105 con espacios en los extremos que queda en 100.
  GREEN: añade el `Field` y el validador.
  Depende: —.
  RF: RF-1, RF-2, RF-3.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T2 — `api/v1/products.py`: fijar a nivel de API la validación y normalización del término**
  Sin cambios de producción previstos: la ruta ya recibe `ProductQuery` por `Query()` (verificado en D1 de plan.md que FastAPI ejecuta el validador). Esta tarea fija ese contrato con tests de API.
  RED: `tests/api/test_products.py` — `term=%20%20` ⇒ `422`, y `client.resolve_warehouse` y `client.search` no se llaman (`assert_not_called`); `term=Leche%20` ⇒ `client.search` recibe `term="leche"` y la respuesta lleva `search.term == "leche"` (RF-4).
  GREEN: si algún caso falla, ajustar el modelo de T1 (no debería hacer falta).
  Depende: T1.
  RF: RF-1, RF-3, RF-4.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T3 — Docs vivas: `README.md` (término)**
  Documenta que `term` se normaliza (espacios de los extremos, espacios internos repetidos, minúsculas), que la respuesta devuelve el término normalizado y que un término vacío, de solo espacios o de más de 100 caracteres responde `422`.
  Depende: T2.
  RF: constitución #9/#10 (docs vivas).
  Hecho cuando: `README.md` recoge las tres reglas, y `ruff check . && ruff format .` no reportan errores sobre los archivos tocados en PR1.

## PR 2 — Total real y paginación

Rama `008-search-completeness-pr2`, base `008-search-completeness-pr1`. Estimación: **≈360 líneas** (plan.md §7, pasos 4-12 de §5). T7 concentra el cambio de firma de `MercadonaClient.search` y la migración de sus mocks en un único commit para no dejar la suite en rojo.

- [x] **T4 — Helper `algolia_response` y migración de las respuestas de Algolia simuladas**
  Nuevo `tests/fixtures/algolia.py` con `algolia_response(hits: list[dict[str, object]], nb_hits: int | None = None, nb_pages: int = 1) -> dict[str, object]` que construye `{"results": [{"hits": hits, "nbHits": nb_hits if nb_hits is not None else len(hits), "nbPages": nb_pages}]}` (D6 de plan.md). Sustituye el cuerpo literal `{"results": [{"hits": [...]}]}` por el helper en los 12 ficheros que lo usan: `tests/integration/test_credential_caching.py`, `test_request_id_correlation.py`, `test_rf1_happy_path.py`, `test_rf2_empty_search.py`, `test_rf3_retry.py`, `test_rf4_cache_hit.py`, `test_rf5_rate_limit.py`, `test_rf_edge_missing_unit_price.py`, `test_rf_edge_redis_down.py`, `test_warehouse_resolution.py`, `tests/scrapers/test_mercadona_client.py` y `test_mercadona_client_retry.py`.
  RED/GREEN: no aplica TDD clásico — refactor de tests sin cambio de comportamiento: hoy `search()` sólo lee `hits`, así que añadir `nbHits`/`nbPages` a las respuestas simuladas no cambia nada. Cada fichero tocado se ejecuta tras el cambio.
  Depende: T3.
  RF: soporte de RF-6, RF-7 (D6).
  Hecho cuando: ningún test construye ya el cuerpo de Algolia a mano y `pytest -q` completo sigue en verde.

- [x] **T5 — `models/mercadona_raw.py`: `RawAlgoliaSearchResult`**
  `RawAlgoliaSearchResult(BaseModel)` con `hits: list[RawAlgoliaProduct]`, `nbHits: int`, `nbPages: int`, todos obligatorios (D3 de plan.md).
  RED: `tests/models/test_mercadona_raw.py` — valida `algolia_response([hit], nb_hits=233, nb_pages=5)["results"][0]` con `nbHits == 233`, `nbPages == 5` y un hit; sin `nbHits` ⇒ `ValidationError`; sin `nbPages` ⇒ `ValidationError`.
  GREEN: añade el modelo.
  Depende: T4.
  RF: RF-6, RF-7.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T6 — `models/query.py`: `page` y `page_size`**
  `page: int = Field(default=1, ge=1)` y `page_size: int = Field(default=50, ge=1, le=100)`. Aditivo: la ruta los acepta pero todavía no los usa (lo hace T7/T8).
  RED: `tests/models/test_query.py` — defaults `page == 1` y `page_size == 50`; acepta `page_size` 1 y 100; rechaza `page` 0 y -1, `page_size` 0 y 101. `tests/api/test_products.py` — `page_size=101` ⇒ `422` sin llamar a `resolve_warehouse` ni a `search`.
  GREEN: añade los dos campos.
  Depende: T5.
  RF: RF-5.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T7 — `MercadonaClient.search(term, warehouse, page, page_size) -> RawAlgoliaSearchResult` y migración de sus mocks**
  El cliente envía `page={page - 1}&hitsPerPage={page_size}` a Algolia (página pública 1-based, Algolia 0-based) y valida `results[0]` completo como `RawAlgoliaSearchResult` (D2). Elimina `_ALGOLIA_HITS_PER_PAGE`. `search_products` pasa `page=query.page, page_size=query.page_size` y usa `result.hits` en lugar de la lista (sin cambiar todavía `total_results` ni la clave: eso es T8). En el mismo commit, migra los mocks de `client.search` a `RawAlgoliaSearchResult`: `tests/api/test_products.py` (3), `tests/api/test_products_errors.py` (2), `tests/services/test_product_search.py` (1), `tests/services/test_product_search_errors.py` (4), `tests/test_main.py` (3).
  RED: `tests/scrapers/test_mercadona_client.py` — `search(..., page=1, page_size=50)` envía `page=0` y `hitsPerPage=50` en los `params` del cuerpo de Algolia; `page=3, page_size=20` envía `page=2` y `hitsPerPage=20`; devuelve `RawAlgoliaSearchResult` con `nbHits`/`nbPages` tal como vienen; respuesta sin `nbHits` ⇒ `ValidationError`. `tests/api/test_products.py` — sin `page`/`page_size` ⇒ `client.search` recibe `page=1, page_size=50` (RF-8).
  GREEN: implementa el cambio de firma y migra los mocks.
  Depende: T6.
  RF: RF-5, RF-6, RF-7, RF-8.
  Hecho cuando: los tests nuevos y los migrados están en verde y `pytest -q` completo sigue en verde.

- [x] **T8 — `SearchMeta` + `search_products`: total real, campos de página, clave nueva y página fuera de rango**
  `SearchMeta` gana `page: int`, `page_size: int`, `total_pages: int`. `search_products`: `total_results = result.nbHits`, `total_pages = result.nbPages`, `page`/`page_size` desde la query (RF-6, RF-7); clave `search:{warehouse}:{query.term}:{query.page}:{query.page_size}` (D5, RF-10); si `query.page > 1` y `result.hits` está vacío ⇒ `raise PageOutOfRangeError` **antes** de escribir en cache (D4, RF-9). Nueva `PageOutOfRangeError(Exception)` en `app/exceptions.py`. Actualiza las construcciones de `SearchMeta` existentes con los campos nuevos: `tests/models/test_product.py`, `tests/services/test_cache.py`, `tests/services/test_cache_resilience.py`, `tests/services/test_product_search.py`.
  RED: `tests/services/test_product_search.py` — resultado con 50 hits y `nb_hits=233, nb_pages=5` ⇒ `total_results == 233`, `total_pages == 5`, `page == 1`, `page_size == 50`, 50 productos; `cache.get` recibe `"search:mad1:leche:1:50"` y con `page=2` `"search:mad1:leche:2:50"`; `page=2` y cero hits ⇒ `PageOutOfRangeError` y `cache.set` no se llama; `page=1` y cero hits ⇒ respuesta normal con lista vacía (regresión spec 001 RF-2). `tests/test_exceptions.py` — `PageOutOfRangeError` instanciable y distinta de `UpstreamUnavailableError`/`PostalCodeNotServedError`.
  GREEN: implementa los campos, el total, la clave y la excepción.
  Depende: T7.
  RF: RF-4, RF-6, RF-7, RF-9, RF-10.
  Hecho cuando: los tests nuevos y actualizados están en verde y `pytest -q` completo sigue en verde.

- [x] **T9 — `api/v1/products.py`: `404` por página fuera de rango**
  `except PageOutOfRangeError` ⇒ `HTTPException(404, detail="Page out of range")`; la descripción de `404` en `responses=` cubre los dos casos (código postal sin servicio y página fuera de rango).
  RED: `tests/api/test_products_errors.py` — `search_products` lanzando `PageOutOfRangeError` (vía `client.search` devolviendo cero hits con `page=2`) ⇒ `404` con `{"detail": "Page out of range"}`.
  GREEN: añade el `except` y actualiza `responses=`.
  Depende: T8.
  RF: RF-9.
  Hecho cuando: los tests nuevos están en verde y `pytest -q` completo sigue en verde.

- [x] **T10 — Integración nueva: `tests/integration/test_search_completeness.py`**
  App real + `lifespan` + fakeredis + respx, cero llamadas reales a Mercadona; `mock_change_pc` de `tests/integration/conftest.py` y `algolia_response` de T4.
  RED: `term=leche` sin página ⇒ 50 productos, `total_results: 233`, `total_pages: 5`, `page: 1`, `page_size: 50` (H1); `page=5` ⇒ el cuerpo enviado a Algolia lleva `page=4` (H2); `page=6` con Algolia devolviendo `hits: []`, `nbHits: 0`, `nbPages: 0` ⇒ `404`, y repetir la petición vuelve a llamar a Algolia porque no se cacheó (RF-9); `term=Leche` y luego `term=leche%20` ⇒ Algolia `call_count == 1` (H4, RF-10); `term=%20%20` ⇒ `422` (H3).
  GREEN: si algún caso falla, ajustar T7-T9 (no debería hacer falta código nuevo).
  Depende: T9.
  RF: RF-1, RF-3, RF-5, RF-6, RF-7, RF-9, RF-10; H1, H2, H3, H4.
  Hecho cuando: todos los casos están en verde en un único archivo y `pytest -q` completo sigue en verde.

- [x] **T11 — Docs vivas: `README.md` (paginación)**
  Parámetros `page` y `page_size` con sus límites, campos nuevos de `SearchMeta` en el ejemplo de respuesta, `total_results` como total real, `404` por página fuera de rango, y el límite de 1000 resultados paginables de Algolia (`total_pages × page_size < total_results`).
  Depende: T10.
  RF: constitución #9/#10 (docs vivas).
  Hecho cuando: el ejemplo de respuesta del README incluye `page`, `page_size` y `total_pages`, y los parámetros nuevos están documentados.

- [x] **T12 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado.
  Depende: T1–T11.
  RF: criterio de finalización de spec.md; constitución #7, #8.
  Hecho cuando: ambos comandos terminan sin error y la cobertura del código nuevo/modificado no baja del 80%.

- [ ] **T13 — Verificación final**
  Con Algolia y `change-pc` mockeados (**nunca contra la API real de Mercadona**): `pytest -q` completo en verde (specs 001-008); `/docs` y `/openapi.json` muestran `page` (mínimo 1), `page_size` (1-100) y los límites de `term`. Verificación manual de spec.md: `term=leche` sin página ⇒ 50 productos, `total_results: 233`, `total_pages: 5`, `page: 1`; `page=5` ⇒ 33 productos; `page=6` ⇒ `404`; `page_size=101` ⇒ `422`; `term=%20%20` ⇒ `422`; `term=Leche` y `term=leche%20` ⇒ una sola llamada a Algolia.
  Depende: T12.
  RF: criterio de finalización de spec.md.
  Hecho cuando: todos los checks manuales y la carga de `/docs` se confirman con mocks.

## Trazabilidad RF → tareas

| RF | Descripción (resumen) | Tareas |
|---|---|---|
| RF-1 | `term` vacío o de solo espacios ⇒ `422` sin llamar a Mercadona | T1, T2, T10 |
| RF-2 | `term` de más de 100 caracteres tras normalizar ⇒ `422` | T1 |
| RF-3 | Normalización del término (extremos, espacios internos, minúsculas) | T1, T2, T10 |
| RF-4 | `SearchMeta.term` devuelve el término normalizado | T2, T8 |
| RF-5 | `page` (≥1, default 1) y `page_size` (1-100, default 50), `422` fuera de rango | T6, T7, T10 |
| RF-6 | `total_results` = `nbHits` real de Algolia | T5, T7, T8, T10 |
| RF-7 | `SearchMeta` + `page`, `page_size`, `total_pages` (= `nbPages`) | T5, T7, T8, T10 |
| RF-8 | Sin `page`/`page_size` ⇒ mismos productos que antes (primera página de 50) | T7 |
| RF-9 | Página > 1 sin resultados ⇒ `404 "Page out of range"`, sin llamada extra ni cache | T8, T9, T10 |
| RF-10 | Clave `search:{warehouse}:{term}:{page}:{page_size}` | T8, T10 |

Todos los RF-1 a RF-10 quedan cubiertos por al menos una tarea; ninguno queda sin mapear.
