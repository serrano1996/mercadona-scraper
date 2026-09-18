# Plan 002 — Medidas antibaneo

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan; las referencias a decisiones de spec 001 se citan como "Dx de plan.md 001".

## 1. Módulos

```
app/
├── scrapers/
│   ├── http_client_factory.py   # NUEVO: USER_AGENTS (pool, spec.md RF-1) + build_mercadona_http_client() -> httpx.AsyncClient
│   └── mercadona_client.py      # MODIFICADO: _request_with_retry gana rama 429 (Retry-After) + jitter en todo backoff
├── services/
│   └── product_search.py        # MODIFICADO: 429 agotado se traduce a UpstreamUnavailableError, igual que 5xx (T13)
├── core/
│   └── config.py                # MODIFICADO: + RETRY_JITTER_MAX_S: float
└── main.py                      # MODIFICADO: usa build_mercadona_http_client() en vez de httpx.AsyncClient() sin headers
```

Cobertura por RF:
- `http_client_factory.py`, `main.py` → **RF-1**
- `mercadona_client.py` → **RF-2, RF-3, RF-4, RF-5**
- `product_search.py` → **RF-6**
- `config.py` → soporte de **RF-5** (RNF)

## 2. Modelo de datos

No hay modelos Pydantic nuevos. Esta spec es comportamiento de red (headers salientes + política de reintento) — los contratos existentes (`ProductOut`, `SearchMeta`, `ProductSearchResponse`, DTOs raw) no cambian.

## 3. Decisiones de diseño

### D1 — Factory dedicada para el `httpx.AsyncClient`, no headers dentro de `MercadonaClient`
**Elegido:** `build_mercadona_http_client() -> httpx.AsyncClient` en un módulo nuevo (`http_client_factory.py`), llamada desde el `lifespan` de `main.py` en vez de `httpx.AsyncClient()` a secas. `MercadonaClient` sigue recibiendo el cliente ya construido — su constructor no cambia.
**Descartado:** poner `random.choice(USER_AGENTS)` dentro de `MercadonaClient.__init__`. Motivo del rechazo: `MercadonaClient` no construye su propio `httpx.AsyncClient` — T17 lo inyecta desde `main.py`. El User-Agent se fija una única vez por instancia de cliente HTTP, y quien controla esa instancia es `main.py`, no `MercadonaClient`. Meterlo dentro de `MercadonaClient` rompería el caso límite que spec.md ya documenta explícitamente: los tests que inyectan su propio `httpx.AsyncClient()` (T9/T10) no deben verse afectados por esta lógica.
RF: **RF-1**.

### D2 — El `429` se maneja dentro de `_request_with_retry` existente, no un método paralelo
**Elegido:** extender la rama ya existente de `_request_with_retry` (T10) con un chequeo explícito `status_code == 429` antes del `if status_code < 500: return response` genérico. **Nota de corrección:** hoy un `429` cae precisamente en esa rama genérica (`429 < 500`) y se devuelve sin reintentar — es un bug real, no sólo una feature nueva; esta spec lo corrige.
**Descartado:** un método `_request_with_retry_429_aware` paralelo, o un decorador aparte. Motivo del rechazo: duplicaría el conteo de intentos y el bucle de backoff ya existente sin necesidad real; un único punto de retry es más fácil de razonar, testear y mantener consistente con D1/D2 de plan.md 001.
RF: **RF-2, RF-3**.

### D3 — `Retry-After`: parseo de los dos formatos HTTP, mismo tope que backoff
**Elegido:** función pura `_parse_retry_after(value: str | None) -> float | None` — intenta `float()` directo (segundos); si falla, `email.utils.parsedate_to_datetime` (formato fecha HTTP) y calcula la diferencia contra "ahora". Mismo enfoque ya validado en `mercadona-scraper-old/http_client.py`. El resultado (o el backoff exponencial si no hay cabecera o no se puede parsear) se limita a `MAX_RETRY_AFTER_S = 60`.
**Descartado:** soportar sólo segundos, ignorando el formato fecha. Motivo del rechazo: el estándar HTTP permite ambos, y el proyecto anterior encontró necesidad real de cubrir los dos — no hay evidencia de que Mercadona/Algolia use sólo uno; más seguro cubrir ambos que asumir.
RF: **RF-2, RF-3, RF-4**.

### D4 — Jitter aditivo sobre el backoff existente, no multiplicativo
**Elegido:** `delay_final = componente_base + random.uniform(0, RETRY_JITTER_MAX_S)`, donde `componente_base` es el `Retry-After` parseado (capado a 60s) o el backoff exponencial ya existente (`RETRY_BASE_DELAY * 2**intento`).
**Descartado:** jitter multiplicativo (`delay * random.uniform(0.5, 1.5)`, patrón "full jitter" de la literatura de AWS). Motivo del rechazo: con `RETRY_BASE_DELAY=0.5` por defecto los delays ya son pequeños (0.5s/1s/2s); un jitter aditivo pequeño y acotado (hasta ~0.3s) rompe el patrón regular sin complicar el cálculo ni arriesgar esperas desproporcionadas en intentos tardíos con backoff exponencial ya grande.
RF: **RF-5**.

### D5 — `RETRY_JITTER_MAX_S` nuevo en `Settings`, no hardcodeado
**Elegido:** `Settings.RETRY_JITTER_MAX_S: float = 0.3`, mismo patrón que `RETRY_BASE_DELAY`/`RETRY_MAX_ATTEMPTS` ya existentes (T2 de spec 001).
**Descartado:** constante hardcodeada en `mercadona_client.py` (como `_ALGOLIA_HITS_PER_PAGE`). Motivo del rechazo: el resto de parámetros de retry ya son configurables vía `Settings`; un jitter no configurable rompería esa consistencia sin motivo, y en tests conviene poder ponerlo a `0` para no ralentizar la suite (mismo patrón ya usado con `RETRY_BASE_DELAY=0.0` en `tests/integration/test_rf3_retry.py`).
RF: soporte de **RF-5**.

### D6 — `429` agotado se mapea a `UpstreamUnavailableError`, no a una excepción nueva
**Elegido:** ampliar la condición ya existente en `product_search.py` (`except httpx.HTTPStatusError as exc: if exc.response.status_code >= 500`) a `status_code >= 500 or status_code == 429`.
**Descartado:** crear `RateLimitedError(UpstreamUnavailableError)` distinta, o propagar un `429` propio en la API pública. Motivo del rechazo: quien está siendo limitado es nuestro scraper contra Mercadona, no el cliente de nuestra API REST contra nosotros — devolverle un `429` a ese cliente sugeriría (incorrectamente) que es él quien debe frenar sus peticiones. `502` ("upstream no disponible") es semánticamente correcto y ya está implementado (T13/T15 de spec 001) — no requiere tocar la capa API.
RF: **RF-6**.

## 4. Estrategia de test

**Unitarios — `mercadona_client.py`** (extiende `tests/scrapers/test_mercadona_client_retry.py` de T10)
- `_parse_retry_after`: segundos válidos, fecha HTTP válida, valor no parseable → `None`, cabecera ausente → `None`.
- `429` con `Retry-After` en segundos → espera ese valor (test con `RETRY_JITTER_MAX_S=0` para determinismo) y reintenta.
- `429` con `Retry-After` en formato fecha → igual.
- `429` sin `Retry-After` → cae al backoff exponencial existente.
- `429` persistente agotando `RETRY_MAX_ATTEMPTS` → propaga `httpx.HTTPStatusError` (429) tras el último intento, mismo mecanismo que 5xx agotado (T10).
- `Retry-After` por encima de 60s → se limita a 60s.
- Un 4xx que no es `429` (ej. 400) → sigue sin reintentar — regresión explícita para no romper D2 de plan.md 001.

**Unitarios nuevos — `http_client_factory.py`** (`tests/scrapers/test_http_client_factory.py`)
- `build_mercadona_http_client()` devuelve un `httpx.AsyncClient` cuyo header `User-Agent` está en `USER_AGENTS`.
- Repetido varias veces, el UA siempre es uno del pool (no se afirma no-determinismo, sólo pertenencia al pool).
- `Accept-Language`/`Referer`/`Origin` presentes con el valor esperado.

**Unitarios — `product_search.py`** (extiende `tests/services/test_product_search_errors.py` de T13)
- `client.search` lanza `httpx.HTTPStatusError(429)` → `product_search` traduce a `UpstreamUnavailableError` (mismo assert que ya cubre 5xx).

**Integración** (extiende `tests/integration/test_rf3_retry.py` de T21)
- Manifest devuelve `429` con `Retry-After` corto, luego `200` → la API responde `200` final (la latencia se absorbe, no se filtra como error al cliente).
- `429` persistente en la cadena → `502` en la API pública (mismo patrón que el 5xx-agotado de T21).

**Cobertura:** mismo objetivo ≥80% de spec 001 (99% real alcanzado) — todo el código nuevo es puro/testeable sin I/O real, no se espera bajarlo.

## 5. Nota sobre verificación en vivo

A diferencia de spec 001, no hay forma honesta de "verificar en vivo contra Mercadona real" que un `429` se maneje bien sin generar tráfico agresivo a propósito — eso contradiría el espíritu mismo de esta spec (no abusar del origen). La verificación manual del criterio de finalización se hace simulando el `429` (mock/`respx`), no provocándolo contra el servicio real.
