# Tasks 011 — Upstream Schema Resilience

Desglose de [plan.md](plan.md). Orden = orden de dependencia (§5 de plan.md). Cada tarea <30 min y es una unidad de trabajo revisable: TDD estricto activo — cada tarea de comportamiento primero escribe el test en rojo (RED), luego el código mínimo para ponerlo en verde (GREEN), y sólo entonces refactoriza, dejando la suite completa en verde al cerrar la tarea (`uv run pytest -q`).

**Cómo se mantiene la suite en verde con el test de integración escrito primero (T1):** los casos que hoy fallan se marcan `@pytest.mark.xfail(strict=True, reason=...)`. Documentan el comportamiento esperado sin romper la suite, y como son `strict`, en cuanto una tarea los arregla pytest falla si la marca sigue puesta: la tarea que los arregla está obligada a quitarla.

## PR único — tolerancia a cambios de esquema de Algolia

Rama `011-upstream-schema-resilience`, base `main`. Estimación: **≈320 líneas** (plan.md §7). La CI valida el PR antes de fusionar.

- [x] **T1 — Integración: `tests/integration/test_upstream_schema_changes.py`**
  App real + `lifespan` + fakeredis + `respx` (`mock_change_pc`, `algolia_response`), con la fixture real `mercadona_algolia_hit_sample.json` modificada en cada caso. Los seis casos de la investigación de spec.md:
  - sin cambios ⇒ `200` (línea base, pasa hoy);
  - sin `popularity_score` ⇒ `200`; sin `objectID` ⇒ `200`; sin `badges.is_water` ⇒ `200`; `price_instructions.selling_method = "kg"` ⇒ `200` (RF-1);
  - sin `price_instructions.unit_price` ⇒ `502`, y una segunda petición igual vuelve a llamar a Algolia porque no se cacheó (RF-3).
  RED: los cinco últimos fallan hoy con `500`. Se confirma ejecutándolos sin marca y después se marcan `xfail(strict=True, reason="spec 011: hoy 500")`.
  Depende: —.
  RF: RF-1, RF-3; H1, H2.
  Hecho cuando: el fichero existe, la línea base pasa, los cinco casos están en `xfail` estricto, y la suite completa sigue en verde.

- [x] **T2 — `mercadona_raw.py` + mapper: modelos reducidos y `unit_price: float`**
  Modelos según plan.md §2: `RawPriceInstructions` con `unit_price: float`, `bulk_price: str | None`, `reference_format: str | None`; `RawAlgoliaCategory` con solo `name` (sustituye a `RawAlgoliaCategoryNode`); `RawAlgoliaProduct` con `id`, `display_name`, `thumbnail`, `categories`, `price_instructions`; se elimina `RawProductBadges` y el resto de campos (D1, D2). El mapper usa `raw.price_instructions.unit_price` sin `float(...)`. Docstring del módulo: la forma completa está en la fixture real.
  RED: `tests/models/test_mercadona_raw.py` — la fixture real valida; valida igual sin `popularity_score`, sin `objectID`, sin `badges`, con `selling_method = "kg"` y con un campo nuevo desconocido; `unit_price` `"5.04"` ⇒ `5.04`, `"abc"` ⇒ `ValidationError`, ausente ⇒ `ValidationError`. Sustituye los tests de `iva` entero y de campos de unidad a `null` (esos campos dejan de existir; el caso "campo no usado con otro tipo" cubre el riesgo de forma general).
  GREEN: reduce los modelos y ajusta el mapper. Quita la aserción de `brand` en `tests/scrapers/test_mercadona_client.py`. Los cuatro casos de campos no usados de T1 pasan a verde: **quita su `xfail`** (si no, fallan por `XPASS(strict)`).
  Depende: T1.
  RF: RF-1, RF-2, RF-3.
  Hecho cuando: los tests de modelo están en verde, los cuatro casos de T1 sin marca y en verde, el caso de `unit_price` sigue en `xfail`, y la suite completa en verde.

- [ ] **T3 — `mercadona_client.py`: `RawAlgoliaResponse` + `AlgoliaResponseInvalid` + log**
  `RawAlgoliaResponse(results: list[RawAlgoliaSearchResult] = Field(min_length=1))` en `mercadona_raw.py`. `MercadonaClient.search` valida `response.content` con `RawAlgoliaResponse.model_validate_json` y devuelve `results[0]`; ante `ValidationError` registra un `WARNING` con, por cada error (máximo cinco), `loc` unido con puntos y `type`, nunca `str(exc)`, `msg` ni `input`, y lanza `AlgoliaResponseInvalid` (nueva, junto a `WarehouseHeaderMissing`) (D3, D4, D5).
  RED: `tests/scrapers/test_mercadona_client.py` — hit sin `unit_price` ⇒ `AlgoliaResponseInvalid`; cuerpos `not json`, `{}` y `{"results": []}` ⇒ `AlgoliaResponseInvalid`; con `unit_price = "PRICE-abc-123"` el `WARNING` contiene `unit_price` y `float_parsing` y **no** contiene `PRICE-abc-123`. `tests/models/test_mercadona_raw.py` — `RawAlgoliaResponse` con `{"results": []}` ⇒ `ValidationError`.
  GREEN: implementa el modelo, la excepción, la validación y el log.
  Depende: T2.
  RF: RF-3, RF-4, RF-5; H3.
  Hecho cuando: los tests nuevos están en verde y la suite completa sigue en verde (el caso de `unit_price` de T1 sigue en `xfail`: ahora da `500` por `AlgoliaResponseInvalid` sin traducir).

- [ ] **T4 — `product_search.py`: `AlgoliaResponseInvalid` ⇒ `502` sin cache**
  `search_products` traduce `AlgoliaResponseInvalid` a `UpstreamUnavailableError` (la ruta ya responde `502`); la excepción sale antes de construir la respuesta, así que no se escribe en cache (D4).
  RED: `tests/services/test_product_search_errors.py` — cliente que lanza `AlgoliaResponseInvalid` ⇒ `UpstreamUnavailableError` y `cache.set` no se llama.
  GREEN: añade la traducción. El caso de `unit_price` de T1 pasa a `502` y no cachea: **quita su `xfail`**.
  Depende: T3.
  RF: RF-3, RF-4.
  Hecho cuando: el test de servicio y los seis casos de T1 están en verde sin ninguna marca `xfail`, y la suite completa en verde.

- [ ] **T5 — Docs, lint, cobertura y CI**
  `README.md`, en "Limitaciones conocidas": la API depende solo de siete campos de Mercadona (`id`, `display_name`, `thumbnail`, `categories[].name`, `price_instructions.unit_price`, `bulk_price`, `reference_format`); un cambio en cualquier otro se ignora, un cambio en uno de estos da `502` y un `WARNING` con la ruta del campo; fila de la spec 011 en la tabla de specs. `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q --cov=app` (≥80%). Verificación contra Algolia real (una consulta, con y sin `attributesToRetrieve=*`): los resultados de `leche` validan con el modelo nuevo. PR con la CI de GitHub en verde.
  Depende: T4.
  RF: criterios de finalización de spec.md; constitución #9/#10.
  Hecho cuando: README actualizado, los tres comandos pasan, la verificación real confirma que ambas consultas validan, y la CI del PR está en verde.

## Trazabilidad RF → tareas

| RF | Descripción (resumen) | Tareas |
|---|---|---|
| RF-1 | Cambios en campos no usados ⇒ búsqueda `200` | T1, T2, T5 |
| RF-2 | Campos nuevos desconocidos ⇒ se ignoran | T2 |
| RF-3 | Campo usado roto ⇒ `502` para toda la búsqueda, sin cache, nunca `500` | T1, T2, T3, T4 |
| RF-4 | Estructura de respuesta inválida ⇒ `502`, no `500` | T3, T4 |
| RF-5 | `WARNING` con la ruta del campo y el tipo de error, sin volcar datos | T3 |

Todos los RF-1 a RF-5 quedan cubiertos por al menos una tarea; ninguno queda sin mapear.
