# Plan 011 — Upstream Schema Resilience

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones y estrategia de test. Numeración de decisiones (D1..) propia de este plan. spec.md no tiene dudas abiertas.

**Hechos verificados el 2026-10-01** con las versiones de `uv.lock`:
- El mapper solo lee `id`, `display_name`, `thumbnail`, `categories[0].name` y `price_instructions.{unit_price, bulk_price, reference_format}`.
- `MercadonaClient.search` hace `RawAlgoliaSearchResult.model_validate(response.json()["results"][0])`: un cuerpo sin `results`, con la lista vacía o que no sea JSON lanza `KeyError`, `IndexError` o un error de JSON, que llegan como `500`.
- Un `unit_price` no numérico (`"abc"`) pasa la validación actual (es `str`) y revienta en el mapper con `float("abc")` ⇒ `500`.
- Declarar `unit_price: float` hace que Pydantic acepte `"6.54"`, `6.54` y `" 6.54"` y rechace `"abc"` (`float_parsing`) en la validación.
- `Model.model_validate_json(...)` convierte en `ValidationError` tanto un cuerpo que no es JSON (`json_invalid`) como uno sin `results` (`missing`); una lista vacía (`{"results": []}`) valida si no se exige longitud mínima.
- `str(ValidationError)` incluye el valor recibido (`input_value=...`); `errors()` da `loc`, `type`, `msg`, `input` y `url` por error. Solo `loc` y `type` son seguros para el log.

## 1. Módulos

```
app/
├── models/
│   └── mercadona_raw.py       # MODIFICADO: modelos reducidos a los campos consumidos;
│                              #   se elimina RawProductBadges; + RawAlgoliaResponse (cuerpo completo)
├── mappers/
│   └── product_mapper.py      # MODIFICADO: unit_price ya llega como float
├── scrapers/
│   └── mercadona_client.py    # MODIFICADO: valida el cuerpo completo; + AlgoliaResponseInvalid
└── services/
    └── product_search.py      # MODIFICADO: AlgoliaResponseInvalid -> UpstreamUnavailableError (502)
```

La ruta (`api/v1/products.py`) no cambia: ya traduce `UpstreamUnavailableError` a `502`. `ProductOut`, `SearchMeta` y la cache tampoco cambian.

Cobertura por RF:
- `mercadona_raw.py` → **RF-1, RF-2, RF-3** (qué es válido)
- `mercadona_client.py` → **RF-3, RF-4, RF-5** (detección y log)
- `product_search.py` → **RF-3, RF-4** (traducción a `502`, sin cache)

## 2. Modelo de datos

Modelos de la respuesta de Algolia tras el cambio (solo lo que consume la app; Pydantic ignora el resto, RF-2):

```python
class RawPriceInstructions(BaseModel):
    unit_price: float  # antes str; ver D2
    bulk_price: str | None  # se usa tal cual en price_format
    reference_format: str | None


class RawAlgoliaCategory(BaseModel):  # antes RawAlgoliaCategoryNode (árbol recursivo)
    name: str


class RawAlgoliaProduct(BaseModel):
    id: str
    display_name: str
    thumbnail: str
    categories: list[RawAlgoliaCategory]
    price_instructions: RawPriceInstructions


class RawAlgoliaSearchResult(BaseModel):  # sin cambios (spec 008)
    hits: list[RawAlgoliaProduct]
    nbHits: int
    nbPages: int


class RawAlgoliaResponse(BaseModel):  # NUEVO: cuerpo completo de /queries
    results: list[RawAlgoliaSearchResult] = Field(min_length=1)
```

Se eliminan `RawProductBadges` y los campos no usados (`slug`, `limit`, `badges`, `status`, `packaging`, `published`, `share_url`, `unavailable_from`, `unavailable_weekdays`, `brand`, `score`, `popularity_score`, `objectID`, y de `price_instructions` todo salvo los tres campos de arriba). La forma completa queda documentada en `tests/fixtures/mercadona_algolia_hit_sample.json`, que es una captura real.

## 3. Decisiones de diseño

### D1 — Modelos reducidos a los campos consumidos
**Elegido:** decidido en spec.md (Dudas #1). Los modelos declaran solo lo que el mapper lee. Un campo no usado que desaparece o cambia de tipo ya no participa en la validación (RF-1); un campo nuevo se ignora como hasta ahora (RF-2).
`RawAlgoliaCategoryNode` pasa a `RawAlgoliaCategory` con solo `name`: el árbol recursivo (`categories` anidado) no se usa, y validarlo era otra fuente de fallos.
RF: **RF-1, RF-2**.

### D2 — `unit_price` como `float` en el modelo crudo
**Elegido:** `unit_price: float`. Pydantic convierte la cadena numérica que envía Mercadona (`"5.04"`) y rechaza una no numérica en la validación, así que **todos** los fallos de un campo usado salen del mismo sitio (la validación) y se tratan igual (RF-3). El mapper deja de hacer `float(...)`.
**Descartado (mantener `str` y validar en el mapper):** el mapper tendría que capturar `ValueError` y traducirlo, un segundo sitio con lógica de "respuesta inválida de Mercadona".
**Descartado (`Decimal`):** el análisis de la mejora 4 mostró que `float` no pierde precisión con dos decimales y la salida pública es `float`.
**Sin efecto en la salida:** `ProductOut.price` ya era `float`; mismo valor.
RF: **RF-3**.

### D3 — Validar el cuerpo completo con `RawAlgoliaResponse.model_validate_json`
**Elegido:** el cliente valida `response.content` entero con `RawAlgoliaResponse` (con `results` de al menos un elemento) y devuelve `results[0]`. Cubre en un solo paso las cuatro formas de respuesta rota de RF-4 verificadas: cuerpo que no es JSON, sin `results`, `results` vacío, y `results[0]` sin `hits`/`nbHits`/`nbPages`.
**Descartado (mantener `response.json()["results"][0]` y capturar `KeyError`, `IndexError` y errores de JSON):** tres tipos de excepción más para el mismo significado.
RF: **RF-4**.

### D4 — `AlgoliaResponseInvalid` en el cliente, traducida a `UpstreamUnavailableError` en el servicio
**Elegido:** `MercadonaClient.search` captura el `ValidationError` de D3, registra el `WARNING` de D5 y lanza `AlgoliaResponseInvalid` (nueva, en `mercadona_client.py`, hermana de `WarehouseHeaderMissing` y `AlgoliaCredentialsUnavailable`). `search_products` la traduce a `UpstreamUnavailableError`, que la ruta ya convierte en `502`. Como la excepción sale antes de construir la respuesta, no se escribe nada en cache (RF-3).
Mismo reparto que la spec 007 con `WarehouseHeaderMissing`: el cliente detecta el fallo de contrato de Mercadona, el servicio lo traduce a dominio.
**Descartado (dejar que `ValidationError` llegue al servicio):** filtra tipos de Pydantic del modelo crudo a través de la capa de servicio.
RF: **RF-3, RF-4**.

### D5 — Log solo con la ruta del campo y el tipo de error
**Elegido:** el `WARNING` lista, por cada error del `ValidationError`, `loc` unido con puntos y `type` (p. ej. `results.0.hits.3.price_instructions.unit_price: float_parsing`), con un máximo de cinco errores. Nunca `str(exc)`, `msg` ni `input`, que incluyen los datos de Mercadona.
RF: **RF-5**.

## 4. Estrategia de test

Todo sin red real: fixture real + `respx` + `AsyncMock`.

**RF-1 / RF-2 / RF-3 — `tests/models/test_mercadona_raw.py`**
- La fixture real valida.
- Validan igual sin `popularity_score`, sin `objectID`, sin `badges`, con `price_instructions.selling_method = "kg"` y con un campo desconocido nuevo (los casos de la investigación).
- `unit_price` `"5.04"` ⇒ `5.04`; `"abc"` ⇒ `ValidationError`; sin `unit_price` ⇒ `ValidationError`.
- Sustituye los tests de `iva` entero y campos de unidad a `null`: esos campos dejan de estar en el modelo, y el test de "campo no usado con otro tipo" cubre el mismo riesgo de forma general.
- `RawAlgoliaResponse`: `{"results": []}` ⇒ `ValidationError`.

**RF-3 / RF-4 / RF-5 — `tests/scrapers/test_mercadona_client.py`**
- Respuesta de Algolia con un hit sin `unit_price` ⇒ `AlgoliaResponseInvalid`; con cuerpo `not json`, `{}` o `{"results": []}` ⇒ `AlgoliaResponseInvalid`.
- El `WARNING` contiene la ruta del campo (`unit_price`) y el tipo de error, y **no** contiene el valor recibido (se usa un valor reconocible, p. ej. `"PRICE-abc-123"`).
- Se quita la aserción de `brand`, que deja de existir en el modelo.

**RF-3 / RF-4 — `tests/services/test_product_search_errors.py`**
- Cliente que lanza `AlgoliaResponseInvalid` ⇒ `UpstreamUnavailableError` y `cache.set` no se llama.

**Integración — `tests/integration/test_upstream_schema_changes.py`** (nuevo)
- App real + `lifespan` + fakeredis + `respx`, con la fixture real modificada: sin `popularity_score`, sin `objectID`, sin `badges.is_water`, `selling_method` como texto ⇒ `200` con el producto; sin `unit_price` ⇒ `502` y la siguiente petición vuelve a llamar a Algolia (no se cacheó). Son exactamente los seis casos de la investigación, que hoy dan `500`.

## 5. Secuencia de implementación (base de tasks.md)

1. Test de integración con los seis casos (todos en rojo hoy salvo el que no cambia nada): fija el comportamiento objetivo antes de tocar código.
2. Modelos reducidos (D1) y `unit_price: float` (D2) + mapper; tests de modelo. Los cuatro casos de campos no usados pasan a verde.
3. `RawAlgoliaResponse` + `AlgoliaResponseInvalid` + log (D3, D4, D5) en el cliente; tests del cliente.
4. Traducción en `search_products`; test de servicio. El caso sin `unit_price` pasa a `502`.
5. README (limitación conocida: qué campos de Mercadona necesita la API) y lint, cobertura, CI.

## 6. Riesgos y notas

- **Menos validación de lo que no se usa:** si Mercadona cambia un campo no usado, ya no se detecta. Es el objetivo de la spec, pero se pierde una señal temprana de cambios de esquema; detectarlos queda fuera de alcance.
- **Un producto roto deja la búsqueda en `502`** (decisión de spec.md, Dudas #2).
- **Las entradas de cache existentes no se ven afectadas:** guardan `ProductSearchResponse`, que no cambia.

## 7. Estimación de líneas cambiadas

| Bloque | Líneas (≈) |
|---|---|
| Código de producción (`mercadona_raw`, `product_mapper`, `mercadona_client`, `product_search`) | 60 añadidas, ≈80 eliminadas |
| Tests nuevos y actualizados | 170 |
| Docs (`README.md`) | 10 |
| **Total** | **≈ 320** |

Por debajo del presupuesto de 400 líneas: **un único PR**, validado por la CI.
