# Plan 006 — Architecture Refactor

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan. Resuelve las 2 dudas abiertas de spec.md con la opción recomendada, confirmada por el usuario.

## 1. Módulos

```
app/
├── core/
│   ├── state.py           # NUEVO: AppState (dataclass) — settings/cache_repository/mercadona_client
│   ├── dependencies.py    # NUEVO: get_settings/get_cache_repository/get_mercadona_client (centralizados)
│   └── security.py        # MODIFICADO: importa get_settings de dependencies.py, borra _get_settings local
├── api/v1/
│   └── products.py        # MODIFICADO: reexporta get_settings/get_cache_repository/get_mercadona_client
│                           #             de dependencies.py, borra sus propias definiciones
└── scrapers/
    └── mercadona_client.py  # MODIFICADO: cachea credenciales de Algolia en memoria de instancia
```

`app/main.py` **no cambia** — el `lifespan` sigue asignando `app.state.settings = ...` etc. exactamente igual (Decisión D4).

Cobertura por RF:
- `mercadona_client.py` → **RF-1, RF-2, RF-3**
- `dependencies.py`, `products.py`, `security.py` → **RF-4, RF-5**
- `state.py`, `dependencies.py` → **RF-6, RF-7**

## 2. Modelo de datos

Un único tipo nuevo, sin persistencia ni Pydantic (no es I/O externo, es estado interno del proceso):

```python
@dataclass
class AppState:
    settings: Settings
    cache_repository: CacheRepository
    mercadona_client: MercadonaClient
```

No hay cambios en `RawAlgoliaProduct`, `ProductSearchResponse` ni ningún modelo de specs anteriores.

## 3. Decisiones de diseño

### D1 — Credenciales de Algolia cacheadas en atributo de instancia, invalidación reactiva
**Elegido:** `MercadonaClient` guarda `self._algolia_credentials: tuple[str, str, str] | None = None` tras el primer `_get_algolia_credentials()` exitoso; llamadas siguientes a `search()` reutilizan ese valor sin repetir las peticiones a `/asset-manifest.json`/bundle. Si Algolia responde `401`/`403` con credenciales cacheadas, se invalida (`None`) y se reintenta **una vez** con credenciales frescas antes de fallar.
**Descartado:** TTL basado en tiempo (ej. re-fetch cada N minutos) — resuelve la duda abierta #1 de spec.md a favor de invalidación reactiva. Motivo del rechazo: un TTL arbitrario necesita un valor que justificar (¿5 min? ¿1h?) sin ninguna señal real de cada cuánto rota Mercadona el bundle; invalidar sólo cuando Algolia efectivamente rechaza la credencial es más simple y correcto por construcción.
RF: **RF-1, RF-2, RF-3**.

### D2 — `_search_algolia()` extraído como método privado, no recursión sobre `search()`
**Elegido:** la construcción de la petición POST a Algolia (hoy inline dentro de `search()`) se extrae a un método privado `_search_algolia(app_id, api_key, index_prefix, term, warehouse)` que `search()` puede llamar dos veces (credenciales cacheadas, y tras invalidar si hace falta) sin duplicar código.
**Descartado:** que el reintento tras un 401/403 llame recursivamente a `search()` completo. Motivo del rechazo: reejecutar `search()` entero volvería a pasar por `_get_algolia_credentials()` sin un límite de profundidad claro — si Algolia devolviera 401 de forma persistente pese a credenciales frescas, el riesgo de recursión indefinida (o de tener que añadir un contador de profundidad ad-hoc) es peor que un método auxiliar reutilizado explícitamente dos veces.
RF: **RF-1, RF-2**.

### D3 — `app/core/dependencies.py` centraliza los tres providers, no sólo `get_settings`
**Elegido:** `get_settings`, `get_cache_repository` y `get_mercadona_client` viven juntos en `app/core/dependencies.py`, aunque spec.md RF-4 sólo señala la duplicación real de `get_settings` (la única que hoy existe por duplicado).
**Descartado:** mover sólo `get_settings` y dejar `get_cache_repository`/`get_mercadona_client` definidos en `products.py`. Motivo del rechazo: los tres acceden a `app.state` de la misma forma y se benefician igual del tipado de RF-6 — separarlos dejaría un provider centralizado/tipado y dos sin mover, una inconsistencia sin motivo real (no hay un segundo consumidor de `get_cache_repository`/`get_mercadona_client` hoy, pero tampoco hay ninguna razón para tratarlos distinto de `get_settings`).
RF: **RF-4, RF-6**.

### D4 — `AppState` como `dataclass` + `typing.cast()` en el punto de acceso, sin tocar el `lifespan`
**Elegido:** `app/core/state.py` define `AppState` (dataclass simple); `app/core/dependencies.py` centraliza el único punto de conversión — `def _state(request: Request) -> AppState: return cast(AppState, request.app.state)` — que cada provider usa internamente. `cast()` no tiene coste en runtime, es sólo información para el type checker; el `lifespan` de `main.py` sigue haciendo `app.state.settings = settings` exactamente igual que hoy.
**Descartado:** el patrón nativo de lifespan-state tipado de Starlette/FastAPI (el `lifespan` retorna un `TypedDict`/mapping que el framework aplica a `request.state`). Resuelve la duda abierta #2 de spec.md a favor de `dataclass` + `cast()`. Motivo del rechazo: ese patrón depende de comportamiento más reciente del framework y añade una capa de indirección (el retorno del `lifespan` deja de ser `None` implícito) sin aportar nada que `cast()` no dé ya para el tamaño de este proyecto — y cumple igual RF-7 (cero cambio de comportamiento en runtime).
RF: **RF-6, RF-7**.

### D5 — `products.py` reexporta los providers de `dependencies.py`, no se tocan los tests existentes
**Elegido:** `app/api/v1/products.py` hace `from app.core.dependencies import get_settings, get_cache_repository, get_mercadona_client` y los reexpone bajo los mismos nombres — cualquier test que hoy haga `from app.api.v1.products import get_settings, get_cache_repository, get_mercadona_client` (specs 001-005) sigue funcionando sin modificarse.
**Descartado:** actualizar los imports en todos los archivos de test que referencian estos providers para que apunten a `app.core.dependencies`. Motivo del rechazo: RF-5 exige explícitamente no romper esos tests — reexportar es un cambio de una línea por símbolo en `products.py`, frente a tocar N archivos de test por un refactor interno que no cambia ningún comportamiento observable.
RF: **RF-5**.

## 4. Estrategia de test

**Unitarios — `mercadona_client.py`**
- Segunda llamada a `search()` sobre la misma instancia, con credenciales ya cacheadas, no repite las peticiones a `/asset-manifest.json`/bundle (respx: `call_count` de esas rutas se mantiene en 1 tras dos búsquedas).
- Algolia responde `401`/`403` con credenciales cacheadas → se invalida el cache, se refetch credenciales una vez, se reintenta la búsqueda con las nuevas — termina en éxito si las credenciales frescas son válidas.
- Si el reintento también falla (`401`/`403` persistente incluso con credenciales frescas) → mismo comportamiento actual, sin cambios (RF-3): la excepción se propaga igual que hoy.

**Unitarios — `app/core/dependencies.py`**
- `get_settings`/`get_cache_repository`/`get_mercadona_client` devuelven exactamente los objetos guardados en `app.state` — mismo comportamiento que las funciones que reemplazan.

**Unitario — `app/core/state.py`**
- `AppState` es instanciable con los tres campos tipados (dataclass trivial, sin lógica adicional que testear).

**Regresión — suite completa**
- Specs 001-005 siguen en verde sin más cambios que los que RF-5 obliga (ninguno, gracias a D5).

**Integración — nueva**
- Primera búsqueda con un `MercadonaClient` recién creado: 3 peticiones HTTP salientes (manifest + bundle + Algolia). Segunda búsqueda sobre la misma instancia: 1 petición (sólo Algolia) — confirmado con `respx` (`call_count`), nunca contra Mercadona real.

**Cobertura:** mismo objetivo ≥80% (specs 001-005 alcanzaron 99% real).

## 5. Nota sobre riesgo y alcance

Este refactor toca `mercadona_client.py`, el módulo más sensible del proyecto (scraping real, ya con incidente de credential-leak documentado en Decisión D7 de plan.md 001). El cambio se limita estrictamente a **dónde** se obtienen las credenciales (cache en memoria vs. fetch por llamada) — no cambia cómo se extraen, ni loguea nunca su valor (sigue aplicando la Decisión D5/T8 de spec 003: nunca loguear secretos). El grep de credenciales filtradas antes de cada commit (hábito ya establecido) sigue aplicando sin cambios.
