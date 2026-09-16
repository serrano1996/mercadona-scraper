# Plan 001 — Mercadona Scraper MVP

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, modelo de datos, decisiones de diseño y estrategia de test.

## 1. Módulos

```
app/
├── main.py            # ensambla FastAPI app, monta routers, lifespan (init/close httpx + redis clients)
├── core/
│   └── config.py      # Settings (pydantic-settings): MERCADONA_BASE_URL, REDIS_URL, CACHE_TTL_SECONDS, RETRY_MAX_ATTEMPTS, RETRY_BASE_DELAY
├── api/
│   └── v1/
│       └── products.py    # GET /api/v1/products — parsea query params, delega a services, mapea excepciones a HTTP
├── models/
│   ├── query.py        # ProductQuery (postal_code, term)
│   ├── product.py       # ProductOut, SearchMeta, ProductSearchResponse (contrato público)
│   └── mercadona_raw.py  # DTOs internos que mapean la forma real del JSON de Mercadona (no expuestos en la API)
├── scrapers/
│   └── mercadona_client.py  # MercadonaClient: httpx.AsyncClient + lógica de retry/backoff, sólo I/O y parseo a DTO raw
├── services/
│   ├── cache.py         # CacheRepository: get/set sobre Redis, TTL, degradación si Redis cae
│   └── product_search.py  # orquesta: cache → scraper → transform (raw DTO → ProductOut) → cache write
└── mappers/
    └── product_mapper.py  # función pura raw DTO → ProductOut / SearchMeta
```

Cobertura por RF:
- `api/v1/products.py`, `models/query.py`, `models/product.py` → **RF-1, RF-2**
- `scrapers/mercadona_client.py` → **RF-1, RF-3**
- `services/cache.py`, `services/product_search.py` → **RF-4**, caso límite "Redis inaccesible"
- `mappers/product_mapper.py` → caso límite "sin precio por unidad" (campo `null`)

## 2. Modelo de datos

**`ProductQuery`** (entrada, query params)
- `postal_code: str` — requerido (ver Decisión D4)
- `term: str` — requerido, búsqueda por texto (RF-1)

**`ProductOut`** (contrato público, por producto)
- `id: str`
- `name: str`
- `price: float`
- `price_format: str | None` — `None` si Mercadona no reporta precio/unidad (caso límite)
- `image_url: str`
- `category: str`

**`SearchMeta`**
- `postal_code: str`, `term: str`, `warehouse: str`, `strategy_used: str`, `scraped_at: datetime`, `total_results: int`

**`ProductSearchResponse`**
- `search: SearchMeta`
- `products: list[ProductOut]` — lista vacía si no hay resultados (RF-2)

**DTO interno `mercadona_raw.*`**: réplica tipada del JSON real de Mercadona, vive solo en `scrapers/`, nunca cruza a `api/`. Justificación en Decisión D6.

RF cubiertos: **RF-1** (forma de la respuesta), **RF-2** (lista vacía), NFR de validación estricta (constitución #4/#5, sin `Any`).

## 3. Decisiones de diseño

### D1 — Retry/backoff hecho a mano, sin librería nueva
**Elegido:** loop propio en `MercadonaClient` con `asyncio.sleep` y backoff exponencial (intentos configurables, base configurable), sólo sobre errores de red o 5xx.
**Descartado:** librería `tenacity`. Motivo del rechazo: constitución #1 fija el stack (httpx, sin extras) y prohíbe añadir libs sin discutirlo antes; para 3 reintentos con backoff exponencial el código propio es trivial y evita una dependencia nueva sin debate.
RF: **RF-3**.

### D2 — No reintentar errores 4xx
**Elegido:** el retry sólo dispara en 5xx/timeout/error de conexión; un 4xx de Mercadona se propaga inmediato.
**Descartado:** reintentar cualquier fallo indiscriminadamente. Motivo del rechazo: un 4xx es determinista (p. ej. parámetro mal formado), reintentar no cambia el resultado y sólo quema presupuesto de latencia (NFR: <1200ms sin caché).
RF: **RF-3**.

### D3 — Cache guarda el modelo ya validado, no la respuesta cruda de Mercadona
**Elegido:** `CacheRepository` serializa `ProductSearchResponse` (post-transformación) con TTL 3600s.
**Descartado:** cachear el JSON crudo de Mercadona y transformarlo en cada hit. Motivo del rechazo: repetir la transformación/validación en cada cache-hit añade coste de CPU en el camino caliente, incompatible con el NFR de <50ms p95 en peticiones cacheadas.
RF: **RF-4**, NFR de rendimiento.

### D4 — `postal_code` requerido en el MVP
**Elegido:** `ProductQuery.postal_code` obligatorio.
**Descartado:** dejarlo opcional hasta resolver la duda abierta de spec.md ("¿es necesario código postal?"). Motivo del rechazo: el ejemplo de RF-1 y el formato de respuesta siempre incluyen `postal_code`/`warehouse`; empezar obligatorio y relajarlo después es un cambio no-breaking (añadir opcionalidad), mientras que empezar opcional y luego exigirlo sí rompe contratos ya publicados. **Asunción explícita, pendiente de confirmación** — no cierra la duda abierta de spec.md, sólo fija el comportamiento por defecto del MVP.
RF: **RF-1**.

### D5 — Redis caído no interrumpe el servicio
**Elegido:** `CacheRepository` envuelve get/set en try/except; si Redis falla, loguea warning y `product_search.py` sigue el camino de scraping directo, sin propagar la excepción.
**Descartado:** patrón circuit breaker (p. ej. `pybreaker`). Motivo del rechazo: overkill para una única dependencia externa (Redis) con un contrato de fallback ya definido en spec.md (caso límite); añade una lib fuera del stack fijo sin necesidad real en el MVP.
RF: caso límite "Caché inaccesible".

### D6 — DTO crudo separado del schema público
**Elegido:** `mercadona_raw.*` (forma real del JSON de Mercadona) vive sólo en `scrapers/`; `mappers/product_mapper.py` traduce a `ProductOut`.
**Descartado:** un único modelo Pydantic reutilizado para parsear la respuesta de Mercadona y servir la API. Motivo del rechazo: acopla el contrato público a un formato interno no documentado de Mercadona; si Mercadona cambia un nombre de campo, con un solo modelo la API rompe en producción, con el mapper separado rompe de forma contenida y visible en el mapper (más fácil de testear y de arreglar).
RF: **RF-1**, NFR de origen de datos.

### D7 — Búsqueda por término: Algolia real, credenciales extraídas de un bundle legacy todavía servido
**Contexto (verificado con peticiones reales, no hipotético):**
1. `tienda.mercadona.es/api/` no tiene endpoint de búsqueda propio: 6 rutas candidatas probadas (`/api/products/?search=`, `/api/search/`, etc.) → 404, o 200 ignorando el parámetro.
2. El bundle JS **actual** de la SPA (`/v9695/index-*.js`, build Vite) confirma que la búsqueda real usa **Algolia** (cliente `algolia-client-js`, headers `x-algolia-api-key`/`x-algolia-application-id`), pero no trae credenciales literales — se inyectan en runtime.
3. `tienda.mercadona.es/asset-manifest.json` (convención de Create React App) **sigue respondiendo 200 hoy** aunque la SPA activa ya no lo referencia — apunta a un bundle legacy (`/v815/static/js/main.*.chunk.js`) de un build anterior de Mercadona.
4. Ese bundle legacy **sí** trae credenciales literales bajo las claves `REACT_APP_ALGOLIA_ID`, `REACT_APP_ALGOLIA_KEY`, `REACT_APP_ALGOLIA_NAME` (valores reales no incluidos aquí a propósito — son un secreto de terceros en producción, no algo para dejar en texto plano en el repo; capturados localmente durante la investigación).
5. **Probado en vivo** (POST real al host `{appId}-dsn.algolia.net`, índice `{index_prefix}_mad1_es`, query "leche"): `200 OK`, 232 resultados reales, mismo catálogo que `/api/categories/`. Confirma que las credenciales siguen activas pese a que el bundle que las expone ya no es el que sirve la home actual.

**Elegido:** `MercadonaClient.search(term, warehouse)` hace 3 llamadas HTTP reales encadenadas: (1) `GET {base}/asset-manifest.json` → resuelve `main.js`; (2) `GET {base}{main.js}` → extrae `appId`/`apiKey`/`index_prefix` por regex sobre el JS; (3) `POST https://{appId}-dsn.algolia.net/1/indexes/*/queries` con índice `{index_prefix}_{warehouse}_es`. Si el regex no encuentra las 3 credenciales, lanza `AlgoliaCredentialsUnavailable` (falla explícito, no un resultado vacío silencioso — Mercadona podría apagar este bundle legacy en cualquier momento). El endpoint de categorías (`/api/categories/{id}/`, T3/T6) se mantiene implementado tal cual, verificado y funcional, pero deja de usarse para búsqueda — queda disponible para una futura función de navegación por categoría si hiciera falta.
**Descartado (versión anterior de esta misma decisión, ya implementada y revertida en esta sesión):** filtrado en cliente recorriendo `/api/categories/{id}/` y comparando `term` contra `display_name`. Motivo del rechazo: dejó de ser necesario en cuanto se confirmó que la búsqueda real (Algolia) sigue siendo alcanzable; category-crawl habría sido más lento (trae de más) y con peor matching que el motor de búsqueda real de Mercadona.
**Descartado (reversear el bundle Vite actual):** el bundle que sirve la home hoy no tiene credenciales literales (confirmado con el mismo regex que sí funciona contra el bundle legacy) — no hay nada que extraer ahí sin ejecutar la SPA real (Playwright/Selenium, prohibido por constitución #2).
**Riesgo asumido y documentado:** este mecanismo depende de que Mercadona siga sirviendo un artefacto legacy no enlazado desde su propia web; si lo retiran, `AlgoliaCredentialsUnavailable` lo hace fallar de forma visible (502 vía T13/T15), no silenciosa. No se implementa fallback automático a category-crawl en el MVP — se documenta aquí como extensión futura si hiciera falta más resiliencia.
RF: **RF-1**. Afecta T9 (re-implementada con Algolia) y la orquestación en `services/product_search.py` (T11/T12, que aún deben resolver el mapeo `postal_code → warehouse`, no cubierto por esta decisión).

## 4. Estrategia de test

Todo en `pytest` + `pytest-asyncio`. Mocks HTTP con `respx` sobre `httpx.AsyncClient` (sin golpear Mercadona real — no determinista, riesgo de bloqueo de IP, y RF-3 exige forzar 5xx a voluntad). Cache mockeada con `fakeredis` o un doble en memoria del `CacheRepository`. **Nota:** `respx`/`fakeredis`/`pytest-asyncio` son dependencias sólo de test, fuera del stack fijo — a discutir/aprobar antes de añadirlas al `pyproject.toml`, según constitución #1.

**Unitarios**
- `product_mapper`: precio sin unidad → `price_format=None` (caso límite), mapeo campo a campo raw→`ProductOut`.
- `MercadonaClient` backoff: función de delay/reintentos aislada del I/O real.
- `CacheRepository`: construcción de la key de cache, TTL aplicado.

**Integración por RF** (contra `TestClient`/`ASGITransport`, Mercadona mockeada con `respx`)
- **RF-1:** `GET /api/v1/products?postal_code=28001&term=leche` con respuesta mockeada → 200, valida forma exacta de `ProductSearchResponse`.
- **RF-2:** término sin resultados → 200, `products: []`.
- **RF-3:** Mercadona devuelve 5xx 3 veces → 502 tras 3 intentos con backoff; y variante 5xx, 5xx, 200 → 200 (retry recupera).
- **RF-4:** primera llamada golpea `MercadonaClient` y hace `SET` en cache con TTL=3600; segunda llamada (mismo query, dentro del TTL) NO vuelve a llamar al scraper (mock `assert_not_called`), sirve desde cache.

**Casos límite**
- Redis caído (`CacheRepository` lanza en connect) → servicio responde 200 vía scraping directo + warning logueado (`caplog`).
- Producto sin precio por unidad → 200, campo `null`, no falla validación Pydantic.

**NFR de rendimiento** (p95 <50ms cacheado / <1200ms sin caché): fuera del alcance de la suite unit/integration estándar; medir aparte (script de benchmark o `pytest-benchmark`, a decidir) — no bloquea "verde" del `pytest` obligatorio de constitución #7, pero sí el criterio de finalización de spec.md.

**Cobertura:** objetivo >80% (criterios de finalización de spec.md), medida con `pytest --cov=app`.

### D8 — Warehouse fijo (`mad1`) en el endpoint, sin resolver `postal_code → warehouse` todavía
**Elegido:** `api/v1/products.py` usa un warehouse hardcodeado (`mad1`) para toda petición, ignorando el `postal_code` real más allá de validarlo como campo requerido (D4). `search_products` ya recibe `warehouse` como parámetro (T11/T12), así que esto es aislado a la ruta — cambiarlo después no toca el servicio.
**Descartado (construir `WarehouseResolver` ahora):** portar/rehacer la lógica del proyecto `mercadona-scraper-old/` (retrieve-pc, change-pc, mapeo postal local) como parte de T14. Motivo del rechazo: es una pieza propia con su propio diseño y tests (ya resuelta una vez en ese proyecto), meterla dentro de "T14 — endpoint" la infla mucho más allá de lo que pide esa tarea; mejor como tarea propia más adelante.
**Descartado (bloquear T14 hasta resolver la duda abierta de spec.md):** no tiene sentido — la duda abierta es sobre si `postal_code` debe ser *obligatorio* (ya resuelto en D4), no sobre cómo resolver el warehouse; son preguntas relacionadas pero distintas, bloquear todo el endpoint por esto para el MVP no aporta.
**Coste asumido:** el MVP no refleja variación regional real de catálogo/precio (RF/NFR no lo exigen explícitamente todavía) — todas las peticiones ven el catálogo de `mad1` sin importar el `postal_code` enviado. Documentado aquí para no perder de vista que es una simplificación temporal, no la solución final.
RF: **RF-1**. Bloqueante pendiente: tarea futura de resolución real `postal_code → warehouse` (candidato: reutilizar el enfoque de `WarehouseResolver` en `mercadona-scraper-old/`).

## 6. Punto abierto heredado de spec.md

La duda **[NECESITA ACLARACIÓN]** sobre si `postal_code`/tienda debe ser obligatorio sigue sin respuesta del negocio. Este plan asume "sí, obligatorio" (Decisión D4) para poder avanzar a diseño de tareas — si la respuesta real es "no", el cambio es aditivo (campo pasa a opcional + lógica de tienda por defecto), no rompe este plan.
