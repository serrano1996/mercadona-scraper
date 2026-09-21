# Tasks 006 — Architecture Refactor

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

- [x] **T1 — `core/state.py`: `AppState`**
  Nuevo `dataclass` `AppState` con `settings: Settings`, `cache_repository: CacheRepository`, `mercadona_client: MercadonaClient` (Decisión D4 en plan.md). Sin lógica, sólo estructura.
  Depende: —.
  RF: soporte de RF-6.
  Hecho cuando: test unitario — `AppState(settings=..., cache_repository=..., mercadona_client=...)` se instancia y expone los tres atributos tal cual; `pytest -q` completo sigue en verde.

- [x] **T2 — `core/dependencies.py`: providers centralizados**
  `get_settings`, `get_cache_repository`, `get_mercadona_client`, todos vía un único `_state(request) -> AppState` que hace `cast(AppState, request.app.state)` (Decisión D3/D4). Mismo comportamiento que las funciones que reemplazan — sólo centralización + tipado.
  Depende: T1.
  RF: RF-4, RF-6.
  Hecho cuando: test unitario — cada provider, dado un `Request` cuyo `app.state` tiene `settings`/`cache_repository`/`mercadona_client` fijados, devuelve exactamente esos objetos (`is`, no sólo `==`).

- [x] **T3 — `core/security.py`: usa `get_settings` de `dependencies.py`**
  Reemplaza `_get_settings` local por `from app.core.dependencies import get_settings`; `verify_api_key` pasa a depender de ese import.
  Depende: T2.
  RF: RF-4.
  Hecho cuando: `pytest -q` completo en verde — `tests/core/test_security.py` no se modifica y sigue pasando tal cual (mismo comportamiento, sólo cambia de dónde viene `get_settings`).

- [x] **T4 — `api/v1/products.py`: reexporta providers de `dependencies.py`**
  Borra `get_settings`/`get_cache_repository`/`get_mercadona_client` locales; importa y reexpone los de `app.core.dependencies` bajo los mismos nombres (Decisión D5) — cualquier `from app.api.v1.products import get_settings, ...` sigue funcionando.
  Depende: T2.
  RF: RF-4, RF-5.
  Hecho cuando: `pytest -q` completo en verde **sin modificar ningún test existente** que importe estos providers desde `app.api.v1.products` (confirma RF-5/D5 — si hiciera falta tocar un test, D5 no se cumplió).

- [x] **T5 — `mercadona_client.py`: cachea credenciales de Algolia en memoria**
  `self._algolia_credentials: tuple[str, str, str] | None = None` en `__init__`; `_get_algolia_credentials()` devuelve el valor cacheado si existe, sin repetir las peticiones a `/asset-manifest.json`/bundle (Decisión D1).
  Depende: —.
  RF: RF-1.
  Hecho cuando: test — segunda llamada a `search()` sobre la misma instancia de `MercadonaClient` no repite las peticiones al manifest/bundle (respx: `call_count` de esas rutas se mantiene en 1 tras dos búsquedas); la suite existente de `tests/scrapers/test_mercadona_client*.py` sigue en verde.

- [x] **T6 — `mercadona_client.py`: invalidación reactiva ante 401/403 de Algolia**
  Extrae `_search_algolia(...)` como método privado (Decisión D2); `search()` detecta `401`/`403` en la respuesta de Algolia, invalida `self._algolia_credentials`, reobtiene credenciales una vez y reintenta — si el reintento también falla, se comporta exactamente igual que hoy (RF-3: sin cambios en la excepción propagada).
  Depende: T5.
  RF: RF-2, RF-3.
  Hecho cuando: test — Algolia responde `401`/`403` con credenciales cacheadas y luego `200` con las credenciales frescas → la búsqueda tiene éxito; test — Algolia responde `401`/`403` con las credenciales frescas también → mismo error final que se propagaba antes del refactor (regresión explícita, no sólo happy path).

- [x] **T7 — Integración: conteo de peticiones salientes confirma el ahorro**
  Sobre `tests/integration/` o `tests/scrapers/`: primera búsqueda con un `MercadonaClient` recién creado hace 3 peticiones (manifest + bundle + Algolia); segunda búsqueda sobre la misma instancia hace 1 (sólo Algolia) — confirmado con `respx`, nunca contra Mercadona real.
  Depende: T6.
  RF: RF-1, RF-3.
  Hecho cuando: test en verde con las aserciones de `call_count` explícitas para ambas búsquedas.

- [x] **T8 — Regresión: suite completa specs 001-005 intacta**
  Confirma que ningún test de specs 001-005 se modificó salvo lo estrictamente necesario (que, gracias a D5, debería ser ninguno).
  Depende: T3, T4, T6, T7.
  RF: RF-5.
  Hecho cuando: `pytest -q` completo en verde; `git diff --stat` sobre `tests/` no muestra cambios fuera de los tests nuevos añadidos en T1-T7 (ningún test preexistente tocado).

- [x] **T9 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que specs 001-005).
  Depende: T1–T8.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80%.
