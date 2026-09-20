# Plan 004 — Authentication

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan.

## 1. Módulos

```
app/
├── core/
│   ├── config.py       # MODIFICADO: + API_KEYS: str (env, coma-separado) + computed_field api_keys: frozenset[str]
│   └── security.py     # NUEVO: verify_api_key(...) — dependency FastAPI, APIKeyHeader + secrets.compare_digest
└── main.py              # MODIFICADO: app.include_router(products_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

`app/api/v1/products.py` **no cambia** — la autenticación se aplica a nivel de router (D1), no dentro del endpoint.

Cobertura por RF:
- `config.py` (`API_KEYS`/`api_keys`) → **RF-5**
- `security.py` (`verify_api_key`) → **RF-1, RF-2, RF-3, RF-4, RF-6**
- `main.py` (registro de la dependency en el router) → **RF-1**

## 2. Modelo de datos

No hay modelos Pydantic de request/response nuevos. Único cambio: `Settings` gana

- `API_KEYS: str` — valor crudo de la variable de entorno, coma-separado (ej. `API_KEYS=app1secret,app2secret`).
- `api_keys: frozenset[str]` — `computed_field` derivado de `API_KEYS` (split por coma, `strip()`, descarta vacíos). Es lo que consume `verify_api_key`; `API_KEYS` no se usa directamente fuera de `config.py`.

## 3. Decisiones de diseño

### D1 — Autenticación a nivel de router (`dependencies=` en `include_router`), no en cada endpoint
**Elegido:** `app.include_router(products_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])` en `main.py` — protege automáticamente cualquier endpoint que se añada bajo `/api/v1/` en el futuro, sin tocarlo.
**Descartado:** añadir `Depends(verify_api_key)` a la firma de cada función de ruta (`get_products`, y las que vengan). Motivo del rechazo: no escala — cada endpoint nuevo tendría que acordarse de añadirlo explícitamente; un olvido deja un endpoint sin protección de forma silenciosa. Aplicarlo a nivel de router lo hace automático y centralizado, y encaja literalmente con el RF-1 ("cualquier endpoint bajo `/api/v1/`").
RF: **RF-1**.

### D2 — `fastapi.security.APIKeyHeader(auto_error=False)` + excepción manual, no el `auto_error=True` por defecto
**Elegido:** `APIKeyHeader(name="X-API-Key", auto_error=False)` como dependencia interna de `verify_api_key` — con `auto_error=False` devuelve `None` (en vez de lanzar) cuando la cabecera falta, así una única función decide el código de estado y el cuerpo de la respuesta tanto para "ausente" como para "inválida".
**Descartado:** dejar `auto_error=True` (comportamiento por defecto de `APIKeyHeader`). Motivo del rechazo: FastAPI devolvería `403 Forbidden` con su formato fijo cuando la cabecera falta, pero necesitaríamos lanzar nosotros un `401` con nuestro propio formato cuando está presente pero es inválida — dos caminos de respuesta distintos para dos casos que RF-3 exige que respondan igual.
RF: **RF-2, RF-3**.

### D3 — `secrets.compare_digest` contra cada token válido, no `in`/`==` directo
**Elegido:** iterar `settings.api_keys` y comparar cada uno con `secrets.compare_digest(received, valid)`; autenticado si alguno coincide.
**Descartado:** `received in settings.api_keys` (usa el hash/`__eq__` normal de `str`, no diseñado para ser constant-time) o `received == token`. Motivo del rechazo: RF-4 exige explícitamente comparación en tiempo constante — `in`/`==` cortocircuitan en el primer carácter distinto y filtran información por temporización, aunque el riesgo práctico para un secreto interno sea bajo, es un NFR explícito de spec.md.
RF: **RF-4**.

### D4 — `Settings.API_KEYS` como `str` plano + `computed_field` a `frozenset[str]`, no `list[str]` con validador
**Elegido:** campo `API_KEYS: str` (valor crudo, coma-separado) + `computed_field` `api_keys: frozenset[str]` que hace `{k.strip() for k in API_KEYS.split(",") if k.strip()}`.
**Descartado:** `API_KEYS: list[str]` con un `field_validator` que parseara el coma-separado directamente. Motivo del rechazo: `pydantic-settings` intenta parsear campos `list[str]` como JSON (`["a","b"]`) antes de aplicar validadores custom — choca con el formato simple coma-separado que RF-5 no exige que sea JSON. Un `str` + `computed_field` evita ese parseo automático y mantiene la env var legible a mano (`API_KEYS=abc,def`), mismo patrón simple que el resto de `Settings`.
RF: **RF-5**.

### D5 — Log de rechazo (RF-6) dentro de `verify_api_key`, no en un middleware aparte
**Elegido:** `logger.warning(...)` dentro de `verify_api_key` (`app/core/security.py`), justo antes de lanzar `HTTPException(401)` — mismo patrón que T7-T9 de spec 003 (loguear junto al punto donde se decide el fallo).
**Descartado:** un middleware separado que inspeccione el status code de la respuesta después de que la ruta termine y loguee si es `401`. Motivo del rechazo: un middleware no puede distinguir "401 por autenticación" de un hipotético "401 de negocio" futuro sin acoplarse a una convención de status code; loguear en el punto exacto de la decisión es más simple y sigue el patrón ya establecido en spec 003.
RF: **RF-6**.

## 4. Estrategia de test

**Unitarios — `config.py`**
- `API_KEYS="a,b,c"` → `Settings().api_keys == {"a", "b", "c"}`.
- Espacios alrededor de las comas (`"a, b ,c"`) se recortan.
- Valor vacío o sólo comas → `api_keys == frozenset()`.

**Unitarios — `security.py` (`verify_api_key`)**
- Sin cabecera `X-API-Key` → `HTTPException(401)`, cuerpo JSON fijo.
- Cabecera vacía (`X-API-Key: `) → mismo `401` que sin cabecera (caso límite de spec.md).
- Cabecera con token que no está en `api_keys` → mismo `401` (idéntico cuerpo al caso anterior — RF-3).
- Cabecera con un token válido (probar con varios tokens configurados, no sólo uno) → no lanza, deja pasar.
- La comparación usa `secrets.compare_digest` (se verifica con `monkeypatch`/spy, mismo patrón que los tests de `mercadona_client.py` que interceptan `random.uniform`/`asyncio.sleep`).
- Rechazo (401) deja una línea `WARNING` en `caplog` con la ruta solicitada, y **nunca** el valor del token recibido (se afirma explícitamente que el token de prueba no aparece en ningún record).

**Integración** (extiende `tests/integration/`)
- `GET /api/v1/products` sin `X-API-Key` → `401`, y `MercadonaClient`/`CacheRepository` mockeados no reciben ninguna llamada (la autenticación corta antes de tocar lógica de negocio — RF-1).
- `GET /api/v1/products` con `X-API-Key` válida → flujo normal sin cambios (reutiliza los mocks de upstream ya existentes en `tests/integration/test_rf1_happy_path.py`), demostrando que D1 no rompe el camino feliz.
- `GET /docs` y `GET /openapi.json` sin `X-API-Key` → `200` (quedan públicos, spec.md "Dudas abiertas" #2 resuelta).

**Cobertura:** mismo objetivo ≥80% (specs 001-003 alcanzaron 99% real).

## 5. Nota sobre compatibilidad con specs anteriores

Ningún test existente de specs 001-003 envía `X-API-Key` hoy — al activar la autenticación (D1), todos esos tests unitarios/integración que golpean `/api/v1/products` directamente empezarán a recibir `401` en vez del código esperado, salvo que se les añada la cabecera. Las tareas de implementación (tasks.md) deben incluir explícitamente actualizar esos tests existentes (fixture/constante compartida con un token válido de pruebas), no sólo añadir tests nuevos — mismo criterio que specs anteriores de "la suite completa sigue en verde", no sólo los tests nuevos.
