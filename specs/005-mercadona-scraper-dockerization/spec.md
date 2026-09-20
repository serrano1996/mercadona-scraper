# Spec 005 — API REST Mercadona Scraper - Dockerization

## Contexto y objetivo

Hoy el proyecto sólo se ejecuta desde un entorno Python local (`uvicorn app.main:app --reload`, dependencias instaladas vía `pyproject.toml` en un venv) y necesita Redis accesible en `localhost` (o la URL que indique `REDIS_URL`). No hay ninguna forma reproducible de construir y ejecutar la API como artefacto autocontenido — cada máquina que la ejecute depende de tener Python 3.11+, las dependencias correctas y un Redis alcanzable ya configurados manualmente.

Objetivo: empaquetar la API en una imagen Docker construible y ejecutable de forma reproducible, con Redis como servicio acompañante para desarrollo/pruebas locales — sin tocar el código de `app/` (`Settings` ya lee toda su configuración de variables de entorno, mecanismo que se reutiliza tal cual).

## Usuarios / actores

- **Desarrollador:** construye y levanta la imagen localmente para probar el sistema completo (API + Redis) sin instalar Python ni Redis en su máquina.
- **Responsable de desplegar el scraper:** usa la imagen como artefacto de despliegue en el entorno que corresponda (el propio contenedor, sin gestionar el proceso Python directamente).

## Historias de usuario

- **H1:** Como desarrollador, quiero construir y levantar la API con un solo comando, para probarla sin instalar Python/Redis localmente.
- **H2:** Como responsable de desplegar el scraper, quiero una imagen que falle rápido y con un error claro si falta configuración obligatoria, para no desplegar un contenedor roto en silencio.
- **H3:** Como responsable de desplegar el scraper, quiero que el propio contenedor/orquestador pueda comprobar si la API está viva sin depender de un endpoint de negocio, para detectar y reiniciar instancias rotas automáticamente.

## Requisitos funcionales (criterios de aceptación en EARS)

- **RF-1:** EL SISTEMA proveerá un `Dockerfile` que construya, a partir del código fuente y `pyproject.toml`, una imagen ejecutable de la API (FastAPI servida por `uvicorn`) — sin requerir ningún cambio en `app/`.
- **RF-2:** CUANDO se construya la imagen, EL SISTEMA instalará únicamente las dependencias de producción declaradas en `pyproject.toml` (excluyendo el grupo `dev`: `pytest`, `ruff`, `respx`, `fakeredis`), para minimizar el tamaño final.
- **RF-3:** EL SISTEMA ejecutará el proceso de la API dentro del contenedor con un usuario sin privilegios de root, no como `root`.
- **RF-4:** EL SISTEMA proveerá un `docker-compose.yml` que levante la API junto a un servicio Redis en la misma red interna, con `REDIS_URL` apuntando al servicio Redis del compose (no a `localhost`).
- **RF-5:** Toda la configuración de `Settings` (`MERCADONA_BASE_URL`, `REDIS_URL`, `API_KEYS`, `LOG_LEVEL`, etc.) será inyectable al contenedor vía variables de entorno o archivo `.env`, sin ningún valor hardcodeado en la imagen — reutilizando el mecanismo ya existente de `pydantic-settings`.
- **RF-6:** SI el contenedor arranca sin las variables de entorno obligatorias (`MERCADONA_BASE_URL`, `REDIS_URL`), EL SISTEMA fallará rápido con el error de validación ya existente de `Settings` (Pydantic `ValidationError`) — no arrancará en un estado parcialmente configurado.
- **RF-7:** EL SISTEMA expondrá el puerto de la API de forma configurable a través de `docker-compose.yml` (por defecto `8000`), mapeado al host.
- **RF-8:** EL SISTEMA proveerá un `.dockerignore` que excluya del contexto de build `.venv/`, `.git/`, `__pycache__/`, `tests/`, `specs/`, `docs/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage` — para builds más rápidos y no filtrar nada innecesario a la imagen.
- **RF-9:** EL SISTEMA expondrá un endpoint `GET /health` que responda `200` sin requerir autenticación (`X-API-Key`) y sin tocar Redis ni Mercadona/Algolia, para servir como sonda de vida (`HEALTHCHECK` de Docker / probes de un orquestador).
- **RF-10:** EL `Dockerfile` declarará una instrucción `HEALTHCHECK` que consulte `GET /health` periódicamente, de forma que `docker ps`/`docker compose ps` reflejen el estado real del contenedor.

## Requisitos no funcionales

- **Sin cambios en `app/`:** toda la dockerización vive en archivos de infraestructura nuevos (`Dockerfile`, `docker-compose.yml`, `.dockerignore`) — el código de la aplicación no se modifica (constitución: cambios mínimos, responsabilidad acotada).
- **Reproducibilidad:** `docker build` desde un checkout limpio produce la misma imagen funcional, sin pasos manuales adicionales.
- **Sin dependencias nuevas de Python:** no se añade ninguna librería a `pyproject.toml` para esta spec (constitución #1) — es exclusivamente infraestructura de contenedores.
- **Nunca credenciales en la imagen:** ningún secreto (tokens de `API_KEYS`, credenciales de Algolia si se hubiesen hardcodeado alguna vez) se copia a la imagen ni se fija por defecto en `Dockerfile`/`docker-compose.yml` — sólo se referencian variables de entorno, mismo criterio que el incidente de credential leak documentado en Decisión D7 de plan.md 001.

## Casos límite

- **`API_KEYS` no configurada en el contenedor:** por defecto vacío (spec 004, T1) — ningún token es válido, todas las peticiones a `/api/v1/*` devuelven `401`. Es el comportamiento *fail-closed* esperado, no un bug de esta spec.
- **Redis no disponible al arrancar el contenedor de la API:** ya gestionado por la degradación existente (Decisión D5, plan.md 001) — el contenedor de la API sigue arrancando y sirviendo peticiones vía scraping directo, con un `WARNING` logueado; esta spec no cambia ese comportamiento, sólo lo hereda.
- **Build sin acceso a red** (para descargar dependencias): fuera de control de esta spec — es una limitación del entorno de build, no del `Dockerfile`.
- **`/health` bajo autenticación por error:** `verify_api_key` (spec 004, D1) sólo se aplica al router montado en `/api/v1/` — `/health` se registra fuera de ese prefijo, igual que `/docs`/`/openapi.json`, así que no requiere `X-API-Key` por construcción, no por una excepción añadida a `verify_api_key`.

## Fuera de alcance

- **Orquestación en Kubernetes/Helm** u otro orquestador — sólo `Dockerfile` + `docker-compose.yml` locales.
- **CI/CD** (build y publicación de la imagen en un registry, GitHub Actions, etc.) — sólo los artefactos de build, no el pipeline que los use.
- **HTTPS/TLS** — se asume, igual que en spec 004, gestionado por un reverse proxy externo al contenedor.
- **Redis gestionado/persistente en producción** — el servicio Redis del `docker-compose.yml` es para desarrollo/pruebas locales; un despliegue real puede apuntar `REDIS_URL` a un Redis gestionado externo sin cambiar nada de esta spec.

## Criterios de finalización

- `docker build` completa sin error y la imagen resultante arranca y responde `200` en `/docs` y en `/health`.
- `docker compose up` levanta API + Redis; `GET /api/v1/products` con token válido responde (con upstream de Mercadona/Algolia simulado, nunca real, mismo criterio que T13 de specs 002/003) sin necesitar ninguna configuración manual adicional dentro del contenedor.
- `docker compose ps` (o `docker ps`) refleja el contenedor de la API como `healthy` una vez arrancado (RF-10).
- El `.dockerignore` excluye `tests/`, `.venv/`, `.git/` del contexto de build (verificable por el tamaño/contenido de la imagen resultante).
- `ruff check .` y `ruff format .` siguen limpios (constitución #8) — no se toca código Python existente salvo el nuevo endpoint `/health`, y se verifica que los archivos de infraestructura no rompen nada.
- Tests: el nuevo endpoint `/health` cuenta con test(s) en verde, cobertura ≥80% del código nuevo/modificado (mismo criterio que specs 001-004).

## Dudas abiertas

Ninguna — resueltas:

1. **`docker-compose.yml` incluye un servicio Redis** para desarrollo/pruebas locales (RF-4) — producción puede seguir apuntando `REDIS_URL` a un Redis externo sin usar ese servicio.
2. **Se añade `GET /health`** dedicado (RF-9/RF-10) — sin autenticación, sin tocar Redis/Mercadona, usado por el `HEALTHCHECK` del `Dockerfile`.
3. **Imagen base `python:3.11-slim`** (no `alpine`).
