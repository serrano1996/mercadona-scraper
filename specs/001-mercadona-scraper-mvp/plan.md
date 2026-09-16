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

## 5. Punto abierto heredado de spec.md

La duda **[NECESITA ACLARACIÓN]** sobre si `postal_code`/tienda debe ser obligatorio sigue sin respuesta del negocio. Este plan asume "sí, obligatorio" (Decisión D4) para poder avanzar a diseño de tareas — si la respuesta real es "no", el cambio es aditivo (campo pasa a opcional + lógica de tienda por defecto), no rompe este plan.
