# Spec 003 — API REST Mercadona Scraper - Logging

## Contexto y objetivo

Hoy el logging del proyecto es mínimo y tiene huecos reales donde un error puede pasar completamente desapercibido:

- No hay ninguna configuración de logging (`logging.basicConfig`/`dictConfig`) en toda la app — sólo 3 llamadas `logger.warning(...)` en todo el código (`app/services/cache.py`, `app/scrapers/mercadona_client.py`), sin nivel/formato configurados, usando el logger raíz por defecto de Python.
- `app/api/v1/products.py` captura `UpstreamUnavailableError` y la convierte en `HTTPException(502)` **sin loguear nada** — un 502 real al cliente no deja ningún rastro propio en los logs.
- `AlgoliaCredentialsUnavailable` (`app/scrapers/mercadona_client.py`) se lanza **sin loguear nada** — si Mercadona retira el bundle legacy del que dependemos (riesgo ya documentado en Decisión D7 de plan.md 001), el fallo es silencioso hasta que alguien mira la excepción en el 502.
- Cuando `_request_with_retry` agota todos los intentos, sólo existen los `logger.warning` por intento individual — no hay un evento final claro de "se agotaron los reintentos".
- Cualquier excepción no prevista explícitamente (un bug real, no un fallo de Mercadona) llega a FastAPI sin pasar por nuestro logger — sólo el logging propio de uvicorn, con formato/nivel no controlado por nosotros.

Objetivo: que cualquier error que ocurra en producción deje una línea de log clara, a nivel adecuado, con contexto suficiente para diagnosticarlo sin reproducirlo — sin añadir dependencias nuevas (constitución #1) ni cambiar el stack.

## Usuarios / actores

- **Sistema:** emite logs durante el ciclo de vida de la app y de cada petición.
- **Responsable de mantener el scraper en producción:** consume esos logs (stderr, capturado por quien despliegue) para detectar y diagnosticar errores sin necesidad de reproducirlos.

## Historias de usuario

- **H1:** Como responsable de mantener el scraper en producción, quiero que cada error (upstream caído, credenciales de Algolia no encontradas, reintentos agotados, o un bug no previsto) deje una línea de log clara con contexto, para detectarlo y diagnosticarlo sin tener que reproducirlo.

## Requisitos funcionales (criterios de aceptación en EARS)

- **RF-1:** CUANDO arranca la aplicación (lifespan de `main.py`), EL SISTEMA configurará el logging raíz una única vez: nivel desde `Settings.LOG_LEVEL` (por defecto `INFO`), formato con timestamp + nivel + logger + mensaje, salida a `stderr` — usando `logging.basicConfig` de la librería estándar, sin dependencias nuevas.
- **RF-2:** CUANDO cualquier excepción no capturada explícitamente llegue al límite de la aplicación, EL SISTEMA la registrará a nivel `ERROR` con traceback completo (`logger.exception`) antes de responder `500` — mediante un exception handler global de FastAPI, sin depender del logging por defecto de uvicorn.
- **RF-3:** CUANDO `product_search.py` traduzca un fallo de `MercadonaClient` en `UpstreamUnavailableError`, EL SISTEMA registrará a nivel `ERROR` el motivo (5xx/429/timeout) y los parámetros de la búsqueda (`postal_code`, `term`) antes de propagarla — hoy este camino no deja ningún rastro pese a resultar en un `502` real al cliente.
- **RF-4:** SI `MercadonaClient._request_with_retry` agota todos los intentos (`RETRY_MAX_ATTEMPTS`), EL SISTEMA registrará ese fallo final a nivel `ERROR` (distinto de los `WARNING` por intento individual ya existentes), incluyendo el número de intentos realizados y la URL.
- **RF-5:** SI la extracción de credenciales de Algolia falla (`AlgoliaCredentialsUnavailable`), EL SISTEMA registrará el evento a nivel `ERROR` antes de propagar la excepción — hoy no deja ningún rastro.
- **RF-6:** CUANDO la API reciba cualquier petición HTTP, EL SISTEMA registrará a nivel `INFO` su inicio (método, ruta, parámetros de consulta) y su fin (status code, duración en ms) — incluidas las peticiones que fallan validación (422) antes de llegar al handler, para poder correlacionar cualquier error logueado con la petición que lo originó.
- **RF-7:** EL SISTEMA generará un identificador único por petición HTTP entrante y lo incluirá en cada línea de log emitida durante su procesamiento, para poder filtrar/correlacionar todos los eventos de una misma petición cuando hay tráfico concurrente.

## Requisitos no funcionales

- **Sin dependencias nuevas:** toda la implementación usa el módulo `logging` de la librería estándar (constitución #1) — nada de `structlog`, `python-json-logger`, ni integraciones externas (Sentry, Datadog).
- **Nunca loguear secretos:** ninguna línea de log incluirá jamás el `X-Algolia-API-Key`/`X-Algolia-Application-Id` extraídos del bundle legacy, ni ninguna otra credencial — lección directa del incidente real de credential leak documentado en Decisión D7 de plan.md 001.
- **Logging síncrono aceptado como excepción:** las llamadas a `logger.*` son síncronas (el módulo `logging` estándar no es async); se acepta como excepción puntual a la asincronía obligatoria (constitución #3) porque el coste de escribir a `stderr` es despreciable frente a la complejidad de un logging async propio.
- **Tipado estricto:** cualquier utilidad nueva (middleware, filtro de request id) usa type hints explícitos, sin `Any` (constitución #4).

## Casos límite

- **Petición con parámetros inválidos** (falta `postal_code` o `term`, Starlette devuelve `422` antes de entrar al handler): también se loguea inicio/fin (RF-6) — implica que el logging de petición vive en middleware ASGI, no dentro de la función de la ruta.
- **Redis caído** (ya gestionado por D5 de plan.md 001, `logger.warning` existente en `cache.py`): sigue como `WARNING`, no `ERROR` — es una degradación esperada y manejada, no un fallo que requiera intervención.
- **Reintento individual fallido pero con éxito final** (ej. recupera al 2º intento): sigue como `WARNING` por intento (ya existente); RF-4 sólo añade el evento `ERROR` cuando se agotan *todos* los intentos.

## Fuera de alcance

- **Logging estructurado en JSON** o cualquier integración con plataformas externas de observabilidad (Sentry, Datadog, ELK, OpenTelemetry) — sólo texto plano a `stderr` vía `logging` estándar.
- **Métricas** (Prometheus) o **tracing distribuido** — esto es logging de errores, no una plataforma de observability completa.
- **Rotación o persistencia de logs a archivo** — se asume que quien despliegue captura `stderr` (systemd, Docker, etc.); no es responsabilidad de la app.

## Criterios de finalización

- RF-1 a RF-7 cuentan con tests (usando `caplog`) en verde, cobertura ≥80% del código nuevo/modificado (mismo criterio que specs 001/002).
- `ruff check .` y `ruff format .` sin errores (constitución #8).
- Verificación manual: provocar cada tipo de error (502 por upstream, credenciales de Algolia no encontradas, reintentos agotados) y confirmar que cada uno deja una línea de log `ERROR` clara y con contexto suficiente para diagnosticarlo sin reproducirlo.

## Dudas abiertas

Ninguna — nivel de log por defecto (`INFO`) es una decisión razonable con default sensato, no bloqueante.
