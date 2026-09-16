# Tasks 001 — Mercadona Scraper MVP

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

## Setup

- [x] **T1 — Scaffolding del proyecto**
  Crear `pyproject.toml` (Python 3.11+, deps: fastapi, pydantic v2, pydantic-settings, httpx, redis), estructura `app/{core,api/v1,models,scrapers,services,mappers}/__init__.py`.
  RF: base (ninguno específico).
  Hecho cuando: `python -c "import app"` no falla; `ruff check .` limpio.

- [x] **T2 — Config (`core/config.py`)**
  `Settings` (pydantic-settings): `MERCADONA_BASE_URL`, `REDIS_URL`, `CACHE_TTL_SECONDS=3600`, `RETRY_MAX_ATTEMPTS=3`, `RETRY_BASE_DELAY`.
  Depende: T1.
  RF: RF-3, RF-4.
  Hecho cuando: test unitario instancia `Settings()` con env vars de prueba y lee `CACHE_TTL_SECONDS == 3600`.

## Modelos

- [x] **T3 — DTO raw de Mercadona (`models/mercadona_raw.py`)**
  Modelos tipados que replican el JSON real de Mercadona (sin `Any`).
  Depende: T1.
  RF: RF-1.
  Hecho cuando: un JSON de ejemplo (fixture) de un producto real de Mercadona valida sin error contra el DTO.

- [x] **T4 — `ProductQuery` (`models/query.py`)**
  Campos `postal_code: str`, `term: str`, ambos requeridos (Decisión D4 de plan.md).
  Depende: T1.
  RF: RF-1.
  Hecho cuando: falta `postal_code` o `term` → `ValidationError`; ambos presentes → instancia válida.

- [x] **T5 — `ProductOut`, `SearchMeta`, `ProductSearchResponse` (`models/product.py`)**
  `price_format: str | None` nullable (caso límite).
  Depende: T1.
  RF: RF-1, RF-2.
  Hecho cuando: `ProductOut(price_format=None, ...)` valida OK; `ProductSearchResponse(products=[])` valida OK.

## Mapeo

- [x] **T6 — `mappers/product_mapper.py`**
  Función pura: DTO raw → `ProductOut` / `SearchMeta`. Si falta precio/unidad → `price_format=None`.
  Depende: T3, T5.
  RF: RF-1, caso límite "sin precio por unidad".
  Hecho cuando: test unitario con fixture sin campo precio-unidad produce `price_format is None`; con campo presente lo copia igual.

## Cache

- [x] **T7 — `services/cache.py`: `CacheRepository` básico**
  `get(key)` / `set(key, value, ttl)` sobre Redis (cliente async), serializa `ProductSearchResponse` a JSON.
  Depende: T5, T2.
  RF: RF-4.
  Hecho cuando: test con `fakeredis` — `set` seguido de `get` devuelve el mismo objeto deserializado.

- [x] **T8 — `CacheRepository`: degradación si Redis cae**
  `get`/`set` envueltos en try/except; log warning; nunca propagan excepción.
  Depende: T7.
  RF: caso límite "Caché inaccesible".
  Hecho cuando: test simula `ConnectionError` en Redis → `get()` devuelve `None` (no lanza) y hay un warning en `caplog`.

## Scraper

- [x] **T9 — `scrapers/mercadona_client.py`: búsqueda real vía Algolia** *(re-diseñada dos veces, ver Decisión D7 de plan.md)*
  No existe endpoint de búsqueda server-side propio en Mercadona. La búsqueda real es Algolia; sus credenciales no están en el bundle Vite actual, pero sí en un bundle legacy (`asset-manifest.json` → `main.js`, convención CRA) que Mercadona sigue sirviendo aunque ya no lo usa — **probado en vivo**, credenciales de julio siguen activas hoy. `MercadonaClient.search(term, warehouse)` encadena 3 llamadas reales: `GET {base}/asset-manifest.json` → `GET {base}{main.js}` (regex `REACT_APP_ALGOLIA_ID`/`KEY`/`NAME`) → `POST https://{appId}-dsn.algolia.net/1/indexes/*/queries` sobre índice `{index_prefix}_{warehouse}_es`. Sin credenciales extraíbles → `AlgoliaCredentialsUnavailable`. Nuevo DTO `RawAlgoliaProduct`/`RawAlgoliaCategoryNode` (shape distinto de `RawProduct` de T3 — categorías anidadas, sin `main_feature`/`is_new_arrival`, con `brand`/`score`/`popularity_score`). Sin retry aún.
  Depende: T2, T3 (reutiliza `RawProductBadges`/`RawPriceInstructions`).
  RF: RF-1.
  Hecho cuando: test con `respx` mockeando las 3 llamadas (formas reales capturadas) → devuelve `list[RawAlgoliaProduct]` parseada correctamente; test con bundle sin credenciales → `AlgoliaCredentialsUnavailable`.

- [x] **T10 — Retry/backoff exponencial**
  Reintenta hasta `RETRY_MAX_ATTEMPTS` sólo en 5xx/timeout/error de conexión (Decisión D1/D2). 4xx no reintenta.
  Depende: T9.
  RF: RF-3.
  Hecho cuando: test con `respx` devolviendo 503 tres veces → se llama 3 veces y se propaga error tras la última; test con 503,503,200 → devuelve 200 en el 3er intento; test con 400 → 1 sola llamada, sin retry.

## Servicio

- [ ] **T11 — `services/product_search.py`: camino cache-hit** ⚠️ *pendiente resolver: mapeo `postal_code → warehouse` (D4 asume `postal_code` obligatorio, pero `MercadonaClient.search` necesita `warehouse`, ej. "mad1" — no hay decisión tomada sobre cómo se resuelve; el proyecto `mercadona-scraper-old/` tenía un `WarehouseResolver` para esto, a evaluar si se reutiliza su enfoque).*
  Si `CacheRepository.get(key)` devuelve algo, retorna directo sin llamar al scraper.
  Depende: T7, T5.
  RF: RF-4.
  Hecho cuando: test con cache pre-poblada → `MercadonaClient.search` mockeado, `assert_not_called()`.

- [ ] **T12 — `services/product_search.py`: camino cache-miss** ⚠️ *mismo pendiente que T11 (mapeo `postal_code → warehouse`).*
  Cache-miss → resuelve `warehouse` desde `postal_code` → llama `MercadonaClient.search(term, warehouse)` → `product_mapper.map_raw_algolia_product_to_product_out` → `CacheRepository.set(ttl=3600)` → retorna.
  Depende: T6, T8, T10, T11.
  RF: RF-1, RF-4.
  Hecho cuando: test con cache vacía → resultado correcto y `CacheRepository.set` llamado una vez con `ttl=3600`.

- [ ] **T13 — Mapeo de error 5xx agotado → excepción de dominio**
  Tras agotar reintentos (T10), el servicio lanza una excepción propia (`UpstreamUnavailableError`) en vez de dejar pasar la excepción de httpx.
  Depende: T12.
  RF: RF-3.
  Hecho cuando: test — tras 3 fallos 5xx simulados, `product_search` lanza `UpstreamUnavailableError`.

## API

- [ ] **T14 — `api/v1/products.py`: endpoint**
  `GET /api/v1/products` parsea query params a `ProductQuery`, llama `product_search`, devuelve `ProductSearchResponse`.
  Depende: T4, T12.
  RF: RF-1, RF-2.
  Hecho cuando: request con término con resultados → 200 + body con `products` no vacío.

- [ ] **T15 — Mapeo `UpstreamUnavailableError` → 502**
  Handler/except en la ruta (o exception handler global) convierte la excepción de T13 en `HTTPException(502)`.
  Depende: T13, T14.
  RF: RF-3.
  Hecho cuando: test — servicio lanza `UpstreamUnavailableError` mockeado → response HTTP 502.

- [ ] **T16 — Término sin resultados → lista vacía**
  Verificar que `product_search`/mapper no fallan con 0 resultados y la ruta responde 200 con `[]`.
  Depende: T14.
  RF: RF-2.
  Hecho cuando: request con término sin resultados (mock Mercadona devuelve 0 productos) → 200, `products == []`.

## Ensamblaje

- [ ] **T17 — `main.py`: lifespan y wiring**
  Crea `FastAPI()`, monta router `api/v1/products`, `lifespan` abre/cierra `httpx.AsyncClient` y conexión Redis.
  Depende: T14.
  RF: base (soporte de todos los RF).
  Hecho cuando: `uvicorn app.main:app` arranca sin error; `/docs` carga y muestra el schema de `ProductSearchResponse`.

## Tests de integración end-to-end (sobre T17)

- [ ] **T18 — Fixtures compartidas de test**
  `conftest.py`: `TestClient`/`ASGITransport`, mock `respx` de Mercadona, `fakeredis` para cache.
  Depende: T17.
  RF: soporte de test (ninguno específico).
  Hecho cuando: un test trivial (`GET /docs` → 200) pasa usando las fixtures.

- [ ] **T19 — Integración RF-1: happy path**
  `GET /api/v1/products?postal_code=28001&term=leche` con Mercadona mockeada → 200, valida forma exacta contra `ProductSearchResponse`.
  Depende: T18.
  RF: RF-1.
  Hecho cuando: test pasa en verde con `pytest`.

- [ ] **T20 — Integración RF-2: búsqueda vacía**
  Depende: T18.
  RF: RF-2.
  Hecho cuando: test pasa, response 200 + `products: []`.

- [ ] **T21 — Integración RF-3: retry y 502**
  Dos variantes: 3×5xx → 502; 5xx,5xx,200 → 200.
  Depende: T18.
  RF: RF-3.
  Hecho cuando: ambos tests pasan en verde.

- [ ] **T22 — Integración RF-4: cache hit evita 2ª llamada**
  Misma query dos veces dentro del TTL → 2ª vez no llama a Mercadona (mock `assert_not_called`).
  Depende: T18.
  RF: RF-4.
  Hecho cuando: test pasa en verde.

- [ ] **T23 — Integración caso límite: Redis caído**
  Mock Redis lanzando `ConnectionError` → response sigue siendo 200 vía scraping directo + warning en logs.
  Depende: T18.
  RF: caso límite "Caché inaccesible".
  Hecho cuando: test pasa, `caplog` contiene el warning.

- [ ] **T24 — Integración caso límite: producto sin precio/unidad**
  Fixture de Mercadona sin ese campo → response 200, `price_format: null`.
  Depende: T18.
  RF: caso límite "sin precio por unidad".
  Hecho cuando: test pasa en verde.

## Cierre

- [ ] **T25 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥ 80%.
  Depende: T19–T24.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura marca ≥80%.

- [ ] **T26 — Verificación manual Swagger**
  Levantar `uvicorn app.main:app`, consultar 3 productos reales desde `/docs`.
  Depende: T25.
  RF: criterio de finalización de spec.md.
  Hecho cuando: las 3 consultas manuales devuelven 200 con datos coherentes.
