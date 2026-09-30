# Plan 008 — Search Completeness

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan; las referencias a otros planes se citan como "Dx de plan.md 00N". spec.md no tiene dudas abiertas. **Depende de spec 007 fusionada** (la ruta ya recibe `Annotated[ProductQuery, Query()]` y la clave de cache ya es por almacén).

## 1. Módulos

```
app/
├── models/
│   ├── query.py               # MODIFICADO: term con normalización + Field(min_length=1, max_length=100);
│   │                          #             + page: int = Field(1, ge=1); + page_size: int = Field(50, ge=1, le=100)
│   ├── product.py             # MODIFICADO: SearchMeta + page, page_size, total_pages
│   └── mercadona_raw.py       # MODIFICADO: + RawAlgoliaSearchResult (hits, nbHits, nbPages)
├── exceptions.py              # MODIFICADO: + PageOutOfRangeError
├── scrapers/
│   └── mercadona_client.py    # MODIFICADO: search(term, warehouse, page, page_size) -> RawAlgoliaSearchResult
├── services/
│   └── product_search.py      # MODIFICADO: clave con página, total real, página fuera de rango
└── api/v1/
    └── products.py            # MODIFICADO: except PageOutOfRangeError -> 404; descripción de 404 en responses=
```

Tests: un helper nuevo para construir respuestas de Algolia (D6), actualización de los mocks existentes de `search()` y de las respuestas de Algolia en integración, y un test de integración nuevo. Docs: `README.md` (parámetros `page`/`page_size`, campos nuevos de `SearchMeta`, `404` por página fuera de rango).

`cache.py`, `warehouse_resolver.py`, `config.py`, `dependencies.py` y `main.py` **no cambian**.

Cobertura por RF:
- `query.py` → **RF-1, RF-2, RF-3, RF-5**
- `product_search.py` → **RF-4, RF-6, RF-7, RF-8, RF-9, RF-10**
- `mercadona_client.py`, `mercadona_raw.py` → **RF-5 (traducción a Algolia), RF-6, RF-7 (datos de origen)**
- `product.py` → **RF-7**
- `products.py`, `exceptions.py` → **RF-9 (mapeo HTTP)**

## 2. Modelo de datos

**`ProductQuery`** (I/O de la API):
- `postal_code: str = Field(pattern=r"^[0-9]{5}$")` — sin cambios.
- `term: str = Field(min_length=1, max_length=100)` con un `field_validator("term", mode="before")` que normaliza (D1).
- `page: int = Field(default=1, ge=1)`.
- `page_size: int = Field(default=50, ge=1, le=100)`.

**`SearchMeta`** (respuesta pública), solo añade campos:
- `total_results: int` — mismo nombre y tipo; **cambia su valor**: `nbHits` real (RF-6).
- `page: int`, `page_size: int`, `total_pages: int` — nuevos (RF-7).

**`RawAlgoliaSearchResult`** (nuevo, espejo tipado de `results[0]` de Algolia, mismo criterio que el resto de `mercadona_raw.py`):
```python
class RawAlgoliaSearchResult(BaseModel):
    hits: list[RawAlgoliaProduct]
    nbHits: int
    nbPages: int
```

**Clave Redis de búsqueda** (D5):

| Antes (spec 007) | Después |
|---|---|
| `search:{warehouse}:{term}` | `search:{warehouse}:{term_normalizado}:{page}:{page_size}` |

## 3. Decisiones de diseño

### D1 — La normalización del término vive en `ProductQuery` (validador `mode="before"`), no en el servicio
**Elegido:** un `field_validator("term", mode="before")` que aplica `" ".join(value.split()).lower()` antes de que se evalúen `min_length`/`max_length`. Así, en un único sitio: un término de solo espacios queda en `""` y lo rechaza `min_length=1` (RF-1); la longitud se mide sobre el término ya normalizado (RF-2); y todo lo que viene después (clave de cache, llamada a Algolia, `SearchMeta.term`) recibe ya el valor normalizado (RF-3, RF-4) sin que nadie más tenga que acordarse de normalizar.
`" ".join(value.split())` cubre a la vez los extremos y los espacios internos repetidos, y trata tabuladores y saltos de línea como espacios.
**Descartado (normalizar en `search_products`):** la validación de longitud y de vacío vería el término crudo, así que `"   "` pasaría la validación y habría que repetir la comprobación en el servicio, y `SearchMeta.term` dependería de que el servicio recuerde usar la versión normalizada.
**Verificado el 2026-09-30** con la versión de FastAPI del proyecto (0.139.2): un modelo con este validador recibido por `Annotated[..., Query()]` normaliza `"  Leche   ENTERA "` a `"leche entera"`, responde `422` a `"   "` y `422` a `page_size=101`. Se fija igualmente con un test de API.
RF: **RF-1, RF-2, RF-3, RF-4**.

### D2 — `MercadonaClient.search` devuelve `RawAlgoliaSearchResult` en vez de `list[RawAlgoliaProduct]`
**Elegido:** `search(term, warehouse, page, page_size) -> RawAlgoliaSearchResult`. El cliente sigue siendo el único que sabe hablar con Algolia: traduce la página pública 1-based a la de Algolia (`page - 1`), pone `hitsPerPage=page_size` y valida `results[0]` completo con Pydantic.
**Descartado (devolver una tupla `(hits, nb_hits, nb_pages)`):** menos tipado y posicional; un orden cambiado no lo detecta nadie.
**Descartado (seguir devolviendo la lista y hacer una segunda llamada para el total):** duplica peticiones a Mercadona en el camino normal, contra el NFR "Sin llamadas extra".
**Coste asumido:** cambia la firma pública del cliente, así que cambian todos los mocks de `client.search` (12 usos en tests) y todas las respuestas de Algolia simuladas con respx (12 ficheros). Se absorbe con el helper de D6.
RF: **RF-5, RF-6, RF-7**.

### D3 — `nbHits` y `nbPages` obligatorios en `RawAlgoliaSearchResult`, sin valor por defecto
**Elegido:** ambos campos requeridos. Algolia los devolvió en todas las respuestas verificadas el 2026-09-30, incluidas la de página fuera de rango y la de término vacío. Si alguna vez faltaran, es un cambio de contrato de Algolia y debe fallar de forma visible.
**Descartado (`nbHits: int = 0` o por defecto `len(hits)`):** justo el error que corrige este spec: un total falso que parece válido.
RF: **RF-6, RF-7**.

### D4 — Página fuera de rango: `PageOutOfRangeError` en el servicio, `404` en la ruta, sin cachear
**Elegido:** `search_products` lanza `PageOutOfRangeError` (nueva, en `app/exceptions.py`, sin tipos de httpx) cuando `query.page > 1` y `hits` viene vacío, **antes** de escribir en cache. La ruta la traduce a `HTTPException(404, detail="Page out of range")`. Con `page == 1` y cero resultados se sigue devolviendo `200` con lista vacía (spec 001 RF-2).
La condición no usa `nbHits` a propósito: Algolia devuelve `nbHits: 0` fuera de rango, así que `nbHits` no distingue "no hay resultados" de "te has pasado de página".
**Descartado (detectarlo en el cliente):** el cliente no sabe qué significa una página vacía para el contrato público; es una decisión de dominio.
**Coste asumido:** `404` pasa a tener dos significados en esta ruta (código postal sin servicio, spec 007; página fuera de rango, este spec). Se distinguen por `detail`, y ambos quedan documentados en `responses=`.
RF: **RF-9**.

### D5 — Clave de cache `search:{warehouse}:{term}:{page}:{page_size}`; las claves antiguas caducan solas
**Elegido:** cada combinación de página y tamaño es una entrada independiente. `term` ya llega normalizado (D1), así que `Leche`, `leche` y `leche ` comparten entrada (RF-10).
**Motivo adicional:** cambiar el formato de la clave **evita leer entradas antiguas** guardadas sin `page`/`page_size`/`total_pages`. Si la clave no cambiara, `ProductSearchResponse.model_validate_json` fallaría al leerlas y `CacheRepository.get` no captura `ValidationError`, así que daría un `500` durante la primera hora tras el despliegue.
**Descartado (una sola entrada por término con todos los resultados):** obligaría a pedir `hitsPerPage=1000` siempre (verificado que funciona), con respuestas y entradas de cache mucho más grandes para servir la primera página, que es el caso habitual.
RF: **RF-10**.

### D6 — Helper de test compartido para respuestas de Algolia
**Elegido:** una función `algolia_response(hits, nb_hits=None, nb_pages=None) -> dict` en `tests/fixtures/algolia.py`, que por defecto usa `len(hits)` y `1`. Todos los mocks respx y los `AsyncMock` de `client.search` pasan a usarla, así la regresión de D2 es un cambio mecánico y uniforme.
**Descartado (añadir `nbHits`/`nbPages` a mano en cada fichero):** mismo resultado, 12 veces repetido y fácil de dejar inconsistente.
**Coste asumido:** los tests usan por defecto un total igual al número de hits, lo que no ejercita la diferencia entre ambos. Los tests nuevos de RF-6 pasan `nb_hits` explícito (p. ej. 233 con 50 hits).

## 4. Estrategia de test

Todo con HTTP mockeado (respx en `tests/scrapers/` e integración, `AsyncMock(spec=...)` en `tests/services/` y `tests/api/`), fakeredis para Redis. **Cero llamadas reales a Mercadona.** Cada bloque es un slice test-first.

**RF-1 / RF-2 / RF-3 / RF-5 — `tests/models/test_query.py`**
- `term`: `"Leche"` → `"leche"`; `"  leche  "` → `"leche"`; `"leche   entera"` → `"leche entera"`; `"\tLeche\n"` → `"leche"`.
- Rechaza `""`, `"   "`, y un término de 101 caracteres tras normalizar. Acepta uno de 100, y uno de 105 con espacios en los extremos que queda en 100.
- `page`: default 1; rechaza 0 y -1. `page_size`: default 50; acepta 1 y 100; rechaza 0 y 101.

**RF-1 / RF-3 / RF-5 a nivel de API — `tests/api/test_products.py`** (fija lo verificado en D1)
- `term=%20%20` → `422` y ni `resolve_warehouse` ni `search` se llaman.
- `term=Leche%20` → `search` recibe `term="leche"`.
- `page_size=101` → `422`. Sin `page`/`page_size` → `search` recibe `page=1, page_size=50` (RF-8).

**RF-5 / RF-6 / RF-7 en el cliente — `tests/scrapers/test_mercadona_client.py`**
- `search(..., page=1, page_size=50)` envía `page=0&hitsPerPage=50` a Algolia; `page=3` envía `page=2`.
- Devuelve `RawAlgoliaSearchResult` con `nbHits`/`nbPages` tal como vienen.
- Respuesta sin `nbHits` → `ValidationError` (D3).

**RF-4 / RF-6 / RF-7 / RF-9 / RF-10 — `tests/services/test_product_search.py`**
- Resultado con 50 hits y `nb_hits=233, nb_pages=5` → `total_results == 233`, `total_pages == 5`, `page == 1`, `page_size == 50`, 50 productos.
- Clave: `cache.get` recibe `"search:mad1:leche:1:50"`; con `page=2` → `"search:mad1:leche:2:50"`.
- `page=2` y cero hits → `PageOutOfRangeError`, y `cache.set` **no** se llama.
- `page=1` y cero hits → respuesta normal con lista vacía (regresión de spec 001 RF-2).

**RF-9 en la ruta — `tests/api/test_products_errors.py`**
- `PageOutOfRangeError` → `404` con `{"detail": "Page out of range"}`.

**Integración — `tests/integration/test_search_completeness.py`** (nuevo, app real + lifespan + fakeredis + respx)
- `term=leche` sin página → 50 productos, `total_results: 233`, `total_pages: 5`, `page: 1`.
- `page=5` → Algolia recibe `page=4`.
- `page=6` → Algolia responde vacío con `nbHits: 0` → `404`; repetir la petición vuelve a llamar a Algolia (no se cacheó).
- `term=Leche` y luego `term=leche%20` → Algolia `call_count == 1` (RF-10).

**Regresión — la suite existente (D2, D6)**
- Los 12 usos de `client.search.return_value`/`side_effect` pasan a devolver `RawAlgoliaSearchResult`.
- Los 12 ficheros con respuestas respx de Algolia pasan a usar `algolia_response(...)`.
- `test_product_search.py` actualiza las claves esperadas al formato nuevo.

## 5. Secuencia de implementación (base de tasks.md)

**PR 1 — Validación y normalización del término** (RF-1 a RF-4; aditivo sobre la búsqueda actual)
1. `ProductQuery.term` con validador y límites (tests de modelo).
2. Tests de API de `422` y de término normalizado que llega a `search` (el código ya funciona tras el paso 1; esta tarea fija a nivel de API lo verificado en D1).
3. README: sección de validación del término.

**PR 2 — Total real y paginación** (RF-5 a RF-10)
4. Helper `algolia_response` y migración de las respuestas respx de Algolia existentes a él (sin cambio de comportamiento: la suite sigue en verde porque hoy se ignoran los campos extra).
5. `RawAlgoliaSearchResult` (tests de modelo).
6. `ProductQuery.page`/`page_size` (tests de modelo).
7. `MercadonaClient.search` con página y tamaño, devolviendo `RawAlgoliaSearchResult`, más la migración de los mocks de `client.search` en el mismo commit (la firma cambia; no puede partirse sin dejar la suite en rojo).
8. `SearchMeta` con campos nuevos, `search_products` con total real, clave nueva y `PageOutOfRangeError`.
9. Ruta: `404` por página fuera de rango y `responses=`.
10. Integración nueva `test_search_completeness.py`.
11. README (`page`, `page_size`, campos nuevos, `404`).
12. Lint, formato y cobertura; verificación final de spec.md.

## 6. Riesgos y notas

- **`404` con dos significados (D4):** un cliente que solo mire el código de estado no distingue "código postal sin servicio" de "página fuera de rango". Aceptado; se documenta y se distingue por `detail`.
- **Límite de 1000 resultados de Algolia:** con términos muy amplios, `total_pages × page_size < total_results`. Se expone tal cual (spec.md, Casos límite); no se intenta sortear.
- **Condición de página fuera de rango y catálogo cambiante:** si el catálogo encoge entre dos peticiones de un cliente que pagina, la última página puede pasar a dar `404`. Es el comportamiento correcto; se documenta.
- **Entradas antiguas de cache:** cubiertas por el cambio de formato de clave (D5). Tras desplegar, la primera petición de cada búsqueda vuelve a llamar a Algolia.
- **Cambio de semántica de `total_results`:** aceptado en spec.md (no hay consumidores externos). Si los hubiera, habría que avisarles.

## 7. Estimación de líneas cambiadas

| Bloque | Líneas (≈) |
|---|---|
| Código de producción (`query`, `product`, `mercadona_raw`, `exceptions`, `mercadona_client`, `product_search`, `products`) | 90 |
| Tests nuevos (modelo, API, cliente, servicio, integración nueva) | 230 |
| Tests existentes actualizados (helper de Algolia en 12 ficheros, mocks de `search` en 12 usos, claves de cache) | 130 |
| Docs (`README.md`) | 20 |
| **Total** | **≈ 470** |

**Supera el presupuesto de 400 líneas por PR.** **Decisión (usuario, 2026-09-30): dos PRs encadenados (PR 1 → PR 2).** Se descarta el PR único con `size:exception`. `tasks.md` debe agrupar las tareas según estos dos PRs. Cada uno queda con la suite en verde al terminar:
- **PR 1** (pasos 1-3, ≈ 110): validación y normalización del término. Ya mejora la tasa de acierto de la cache y cierra el caso del catálogo entero.
- **PR 2** (pasos 4-12, ≈ 360): total real y paginación. El paso 7 concentra el cambio de firma del cliente y su migración de mocks en un solo commit para no dejar la suite en rojo.

A diferencia del PR 3 de la spec 007, **ningún commit intermedio deja tests en rojo**.
