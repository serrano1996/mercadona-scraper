# Tasks 004 — Authentication

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

- [x] **T1 — `Settings.API_KEYS` + `api_keys` computed field**
  Nuevo campo `API_KEYS: str` (env var, coma-separado, ej. `API_KEYS=app1secret,app2secret`) y `computed_field` `api_keys: frozenset[str]` que hace `{k.strip() for k in API_KEYS.split(",") if k.strip()}` (Decisión D4 en plan.md).
  Depende: —.
  RF: soporte de RF-5.
  Hecho cuando: test unitario — `Settings(API_KEYS="a,b,c").api_keys == {"a", "b", "c"}`; espacios alrededor de las comas se recortan; `API_KEYS=""` (o sólo comas) da `frozenset()`.

- [x] **T2 — `core/security.py`: `verify_api_key` — cabecera ausente/vacía → 401**
  Nueva dependencia FastAPI `verify_api_key(...)` usando `APIKeyHeader(name="X-API-Key", auto_error=False)` (Decisión D2). Si el valor es `None` o cadena vacía, lanza `HTTPException(401, detail=...)` con un cuerpo JSON fijo.
  Depende: T1.
  RF: RF-2.
  Hecho cuando: test unitario — llamar la dependencia sin cabecera, y con cabecera vacía (`X-API-Key: ""`), ambos casos lanzan `HTTPException` con `status_code == 401` y el mismo `detail`.

- [x] **T3 — `core/security.py`: comparación de token contra `settings.api_keys` (tiempo constante)**
  Extiende `verify_api_key`: si la cabecera está presente, compara contra cada token de `settings.api_keys` con `secrets.compare_digest` (Decisión D3); ninguna coincidencia → mismo `HTTPException(401)` y mismo `detail` que T2 (RF-3: sin distinguir "ausente" de "inválida"); alguna coincidencia → no lanza, la dependencia retorna.
  Depende: T1, T2.
  RF: RF-1, RF-3, RF-4.
  Hecho cuando: test unitario — token que no está en `api_keys` → mismo `401`/`detail` que T2; token que sí está (probado con varios tokens configurados a la vez, no sólo uno) → no lanza; se verifica (vía `monkeypatch`/spy) que la comparación pasa por `secrets.compare_digest`, no por `==`/`in` directo.

- [x] **T4 — `core/security.py`: log `WARNING` en rechazo, sin loguear el token**
  Dentro de `verify_api_key`, justo antes de cada `HTTPException(401)` (los de T2 y T3): `logger.warning(...)` con la ruta solicitada (Decisión D5) — nunca el valor de la cabecera recibida.
  Depende: T3.
  RF: RF-6.
  Hecho cuando: test — un rechazo (ausente e inválida, ambos casos) deja una línea `WARNING` en `caplog`; se afirma explícitamente que el token de prueba usado no aparece en el texto de ningún record.

- [x] **T5 — `main.py`: aplica `verify_api_key` a `/api/v1/`**
  `app.include_router(products_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])` (Decisión D1).
  Depende: T4.
  RF: RF-1.
  Hecho cuando: test — `GET /api/v1/products` sin cabecera → `401` a través de la app real (antes tocaba lógica de negocio, ahora no).

- [x] **T6 — Actualiza tests existentes (specs 001-003) con una cabecera `X-API-Key` válida**
  Añade una constante/fixture compartida con un token de pruebas (ej. en `tests/conftest.py` o un fixture de `tests/integration/conftest.py`) y actualiza **todos** los tests existentes que golpean `/api/v1/products` directamente (`tests/api/`, `tests/integration/`, `tests/test_main.py`) para enviarla — ver nota de compatibilidad en plan.md sección 5.
  Depende: T5.
  RF: regresión — mantiene en verde specs 001-003 tras activar RF-1.
  Hecho cuando: `pytest -q` completo en verde (no sólo los tests nuevos de esta spec).

- [x] **T7 — Integración: petición sin `X-API-Key` no toca lógica de negocio**
  Sobre `tests/integration/`: `GET /api/v1/products` sin cabecera → `401`, y los mocks de `MercadonaClient`/`CacheRepository`/respx no reciben ninguna llamada (la autenticación corta antes).
  Depende: T5.
  RF: RF-1.
  Hecho cuando: test de integración en verde, con aserciones explícitas de "no llamado" sobre los mocks/rutas respx.

- [ ] **T8 — Integración: `/docs` y `/openapi.json` siguen públicos**
  Sobre `tests/test_main.py` (ya cubre `test_docs_load`/`test_openapi_schema_...`): confirma explícitamente que ambos responden `200` **sin** cabecera `X-API-Key` (spec.md, duda abierta #2 resuelta).
  Depende: T5.
  RF: caso límite de spec.md.
  Hecho cuando: test — `GET /docs` y `GET /openapi.json` sin cabecera → `200`.

- [ ] **T9 — Integración: camino feliz sin cambios con token válido**
  Reutiliza el mock de upstream de `tests/integration/test_rf1_happy_path.py`, añadiendo la cabecera `X-API-Key` válida (fixture de T6): confirma que D1 no altera el flujo ni la respuesta esperada.
  Depende: T6.
  RF: regresión de D1.
  Hecho cuando: test en verde, misma respuesta exacta que `test_get_products_returns_exact_response_shape` (T19 de spec 001) pero pasando por la autenticación.

- [ ] **T10 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio; `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que T12/T25 de specs 001-003).
  Depende: T1–T9.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80%.

- [ ] **T11 — Verificación manual**
  Levantar `uvicorn app.main:app`; probar con `curl`/similar: sin cabecera (401), con cabecera inválida (401), con cabecera válida (200/502 según upstream), y confirmar que ningún log expone el valor de `X-API-Key` en ningún caso.
  Depende: T10.
  RF: criterio de finalización de spec.md.
  Hecho cuando: los tres casos devuelven el código esperado y los logs de rechazo no contienen el token probado.
