# Spec 006 — API REST Mercadona Scraper - Architecture Refactor

## Contexto y objetivo

Tras cerrar las specs 001-005 (MVP, anti-baneo, logging, autenticación, dockerización), una revisión de arquitectura sobre el código actual identificó tres mejoras concretas, ninguna motivada por un bug ni por un requisito nuevo — son mejoras de mantenibilidad/eficiencia sobre comportamiento ya correcto:

1. **`MercadonaClient.search()` ([mercadona_client.py:96](../../app/scrapers/mercadona_client.py)) no cachea las credenciales de Algolia.** Cada búsqueda con *cache miss* de Redis repite `_get_algolia_credentials()` — dos peticiones HTTP a Mercadona (`/asset-manifest.json` + el bundle JS legacy) — antes de llegar siquiera a Algolia. `MercadonaClient` vive toda la vida del proceso (instanciado una vez en el `lifespan`, spec 001), así que esas credenciales podrían reutilizarse en memoria: cambian solo si Mercadona redespliega el bundle legacy, no en cada búsqueda. Cachearlas reduce tráfico saliente hacia Mercadona en cache-misses — directamente alineado con el objetivo de spec 002 (anti-baneo).
2. **`get_settings`/`_get_settings` duplicados.** [`app/api/v1/products.py:24`](../../app/api/v1/products.py) y [`app/core/security.py:25`](../../app/core/security.py) definen la misma función (`return request.app.state.settings`) por separado, para evitar un import circular entre ambos módulos. Es la única pieza de la arquitectura actual con lógica idéntica duplicada en dos sitios.
3. **`app.state` como contenedor de DI sin tipar.** `Settings`, `CacheRepository` y `MercadonaClient` se guardan en `request.app.state.*` — un `SimpleNamespace` sin verificación estática de tipos. Funciona, pero un typo en un atributo (`app.state.cach_repository`) no lo detectaría el type checker, solo un fallo en runtime.

Objetivo: aplicar las tres mejoras sin cambiar ningún comportamiento observable de la API — mismos RF de specs 001-005, misma suite de tests en verde (con las actualizaciones estrictamente necesarias para el nuevo módulo compartido).

## Usuarios / actores

- **Desarrollador que mantiene el scraper:** se beneficia de menos duplicación y de errores de tipeo en `app.state` detectados en desarrollo, no en producción.
- **Sistema:** genera menos tráfico saliente hacia Mercadona en cache-misses repetidos con el mismo término/código postal en corto plazo (aunque cada término distinto siga necesitando una búsqueda real).

## Historias de usuario

- **H1:** Como responsable de mantener el scraper, quiero que las credenciales de Algolia se reutilicen en memoria entre búsquedas, para reducir peticiones innecesarias a Mercadona y acercarnos más al espíritu de spec 002.
- **H2:** Como responsable de mantener el scraper, quiero un único punto de definición para `get_settings`, para no tener que mantener dos implementaciones idénticas sincronizadas.
- **H3:** Como responsable de mantener el scraper, quiero que el estado compartido de la app esté tipado, para que un error de atributo se detecte en desarrollo (type checker/IDE) en vez de en producción.

## Requisitos funcionales (criterios de aceptación en EARS)

### Cache de credenciales Algolia

- **RF-1:** CUANDO `MercadonaClient.search()` se invoque y la instancia ya tenga credenciales de Algolia obtenidas en una llamada anterior, EL SISTEMA reutilizará esas credenciales en memoria en lugar de repetir las peticiones a `/asset-manifest.json` y al bundle JS legacy.
- **RF-2:** SI Algolia responde a una búsqueda con un error de autenticación (`401`/`403`) usando credenciales cacheadas, EL SISTEMA invalidará el cache en memoria y reintentará obtener credenciales frescas una única vez antes de fallar — cubre el caso en que Mercadona rota las credenciales del bundle sin que el proceso se reinicie.
- **RF-3:** El comportamiento observable de `search()` no cambia: mismos resultados, mismos errores (`UpstreamUnavailableError`, `AlgoliaCredentialsUnavailable`), mismos logs de specs 002/003 — la única diferencia es que las peticiones a manifest/bundle se omiten cuando ya hay credenciales cacheadas válidas.

### Provider de `Settings` compartido

- **RF-4:** EL SISTEMA expondrá una única función `get_settings(request: Request) -> Settings` en un módulo común nuevo (`app/core/dependencies.py`), consumida tanto por `app/api/v1/products.py` como por `app/core/security.py` — elimina la duplicación actual (`get_settings` en `products.py`, `_get_settings` en `security.py`).
- **RF-5:** Los tests existentes que hoy importan `get_settings` desde `app.api.v1.products` para `dependency_overrides` (specs 001-005) seguirán funcionando sin cambiar su comportamiento — mediante re-exportación desde `products.py` o actualización de los imports de los tests (decisión de implementación, ver plan.md).

### Tipado de `app.state`

- **RF-6:** EL SISTEMA definirá una clase dedicada (p.ej. `AppState`) que declare explícitamente los atributos `settings: Settings`, `cache_repository: CacheRepository` y `mercadona_client: MercadonaClient`, de forma que el acceso a `request.app.state.*` quede verificado por el type checker.
- **RF-7:** El comportamiento en runtime no cambia: mismos objetos, mismo ciclo de vida (creados en el `lifespan` de `main.py`, liberados al cerrar) — el cambio es exclusivamente de tipado estático, sin lógica nueva.

## Requisitos no funcionales

- **Sin cambios de comportamiento observable:** todos los RF de specs 001-005 (respuestas HTTP, códigos de estado, logs, autenticación, contrato del endpoint) siguen cumpliéndose exactamente igual — este refactor no es una feature.
- **Sin dependencias nuevas:** las tres mejoras se implementan con la librería estándar y el stack ya fijado (constitución #1).
- **Tipado estricto:** `AppState` (RF-6) y cualquier utilidad nueva usan type hints explícitos, sin `Any` (constitución #4).
- **Suite de tests intacta salvo lo estrictamente necesario:** ningún test existente cambia su aserción — sólo los imports que RF-5 obliga a tocar.

## Casos límite

- **Concurrencia en el primer cache-miss de credenciales:** varias peticiones simultáneas con el cache de credenciales aún vacío podrían disparar fetches duplicados en paralelo (no se serializa el refresco con un lock). No es una regresión — hoy **todas** las búsquedas con cache-miss ya duplican esto en cada llamada — y añadir un lock introduciría complejidad no justificada por spec.md.
- **Mercadona retira el bundle legacy definitivamente** (riesgo ya documentado en Decisión D7, plan.md 001): tras invalidar el cache por un 401/403 de Algolia, el intento de refresco fallaría con `AlgoliaCredentialsUnavailable` — comportamiento ya existente (spec 003, T8), sin cambios.
- **Reinicio del proceso:** el cache de credenciales es puramente en memoria de la instancia de `MercadonaClient` — un reinicio del proceso (redeploy, restart del contenedor) lo vacía y la primera búsqueda tras el reinicio vuelve a pagar el coste de manifest+bundle. Comportamiento esperado, no un bug.

## Fuera de alcance

- **Extraer el retry/backoff de `MercadonaClient` a una clase reutilizable aparte** — evaluado durante el análisis, descartado por ahora: sólo hay un caller real (`MercadonaClient` mismo), separar sería sobre-ingeniería sin un segundo consumidor que lo justifique.
- **Generalizar `CacheRepository` más allá de Redis** — descartado: la constitución fija Redis como cache (constitución #1), no hay ningún requisito de soportar otro backend.
- **Cualquier cambio de comportamiento observable de la API** — specs 001-005 quedan intactas; esto es refactor interno puro.
- **Cache distribuido de credenciales entre réplicas** (si el scraper se despliega con >1 instancia) — cada instancia mantiene su propio cache en memoria, sin coordinación entre réplicas. No se pide en spec.md y añadiría una dependencia de coordinación (Redis para esto también) no justificada por el volumen actual.

## Criterios de finalización

- RF-1 a RF-7 cuentan con tests en verde, cobertura ≥80% del código nuevo/modificado (mismo criterio que specs 001-005).
- La suite completa existente (specs 001-005) sigue en verde, sin más cambios que los imports que RF-5 exige.
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación manual: contar (vía `caplog`/mock con `call_count`, nunca contra Mercadona real) que una segunda búsqueda con cache-miss de Redis pero credenciales ya cacheadas hace 1 petición HTTP saliente (a Algolia) en vez de 3 (manifest + bundle + Algolia).

## Dudas abiertas

Ninguna — resueltas, confirmadas por el usuario con la opción recomendada:

1. **Cache de credenciales con invalidación reactiva** (no TTL) — plan.md Decisión D1.
2. **`AppState` como `dataclass` + `typing.cast()`** (no el patrón de lifespan-state nativo) — plan.md Decisión D4.
