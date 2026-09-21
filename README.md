# Mercadona Scraper API

API REST asíncrona construida con FastAPI que expone la búsqueda de productos de Mercadona. Extrae datos del backend real de búsqueda de Mercadona (Algolia), los valida y transforma con Pydantic, y cachea los resultados en Redis para minimizar peticiones innecesarias. Protegida con autenticación por token y pensada para ejecutarse tal cual en Docker.

Proyecto académico (TFM), desarrollado siguiendo **Spec-Driven Development (SDD)**: cada funcionalidad nace de una spec en `specs/`, revisada y aprobada antes de escribir una sola línea de código.

## Índice

- [Stack](#stack)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos](#requisitos)
- [Instalación y ejecución local](#instalación-y-ejecución-local)
- [Variables de entorno](#variables-de-entorno)
- [Uso de la API](#uso-de-la-api)
- [Docker](#docker)
- [Tests y calidad](#tests-y-calidad)
- [Desarrollo dirigido por especificaciones (SDD)](#desarrollo-dirigido-por-especificaciones-sdd)
- [Limitaciones conocidas](#limitaciones-conocidas)

## Stack

- **Python 3.11+**, tipado estricto (sin `Any` en anotaciones públicas)
- **FastAPI** + **uvicorn** — API asíncrona
- **Pydantic v2** / **pydantic-settings** — validación de datos y configuración
- **httpx** (async) — cliente HTTP hacia Mercadona/Algolia
- **Redis** — cache de resultados de búsqueda
- **pytest** + **pytest-asyncio** + **respx** + **fakeredis** — tests (nunca contra Mercadona real)
- **ruff** — lint y formato
- **Docker** / **docker-compose** — empaquetado y ejecución reproducible

Ningún scraping vía navegador (Playwright/Selenium) ni parsing de HTML (BeautifulSoup): todo el acceso a Mercadona es contra sus endpoints JSON internos. Ver [docs/constitution.md](docs/constitution.md) para las reglas completas del proyecto.

## Estructura del proyecto

```
app/
├── api/v1/products.py       # Endpoint GET /api/v1/products
├── core/
│   ├── config.py             # Settings (pydantic-settings, lee variables de entorno)
│   ├── dependencies.py       # Providers de FastAPI (settings/cache/cliente), centralizados
│   ├── state.py               # AppState — tipado del estado compartido de la app
│   ├── security.py           # Autenticación por X-API-Key
│   └── logging_config.py     # Configuración de logging + correlación por request-id
├── middleware/request_logging.py  # Logging de inicio/fin de cada petición
├── models/                   # Schemas Pydantic (entrada/salida de la API y datos crudos)
├── mappers/                  # Transforma datos crudos de Mercadona al schema de salida
├── scrapers/
│   ├── mercadona_client.py   # Cliente Algolia: credenciales, búsqueda, reintentos
│   └── http_client_factory.py # httpx.AsyncClient con rotación de User-Agent
├── services/
│   ├── cache.py              # Repositorio de cache sobre Redis
│   └── product_search.py     # Orquesta cache -> scraper -> respuesta
└── main.py                   # Ensamblado de la app, lifespan, middleware, /health

specs/            # Specs SDD (spec.md / plan.md / tasks.md por feature)
docs/constitution.md  # Reglas y principios del proyecto
tests/            # Unitarios + integración, misma estructura que app/
Dockerfile        # Build multi-stage (builder + runtime, usuario no-root)
docker-compose.yml  # API + Redis para desarrollo/pruebas locales
```

## Requisitos

- Python 3.11 o superior
- Redis accesible (local, contenedor, o gestionado) — no necesario si solo vas a correr los tests (usan `fakeredis`)
- Docker + Docker Compose (opcional, para ejecución containerizada)

## Instalación y ejecución local

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env             # y rellena los valores (ver siguiente sección)

uvicorn app.main:app --reload
```

La API queda disponible en `http://localhost:8000`, con documentación interactiva en `http://localhost:8000/docs`.

## Variables de entorno

Configuradas vía `.env` (ver `.env.example`) o variables de entorno reales — `Settings` (pydantic-settings) las valida al arrancar; si falta una obligatoria, el proceso falla rápido con un error claro en vez de arrancar en un estado roto.

| Variable              | Obligatoria | Default  | Descripción                                                                 |
| ---------------------- | :---------: | -------- | ---------------------------------------------------------------------------- |
| `MERCADONA_BASE_URL`    |     Sí      | —        | Base URL de tienda.mercadona.es (origen del manifest/bundle legacy)          |
| `REDIS_URL`             |     Sí      | —        | URL de conexión a Redis (ej. `redis://localhost:6379/0`)                     |
| `API_KEYS`              |     No      | `""`     | Tokens válidos separados por coma para `X-API-Key`; vacío = nadie autentica  |
| `CACHE_TTL_SECONDS`     |     No      | `3600`   | TTL de las entradas de cache de búsqueda                                     |
| `RETRY_MAX_ATTEMPTS`    |     No      | `3`      | Intentos máximos por petición saliente a Mercadona/Algolia                   |
| `RETRY_BASE_DELAY`      |     No      | `0.5`    | Delay base (segundos) del backoff exponencial entre reintentos               |
| `RETRY_JITTER_MAX_S`    |     No      | `0.3`    | Jitter aleatorio máximo (segundos) añadido a cada delay de reintento         |
| `LOG_LEVEL`             |     No      | `INFO`   | Nivel de logging raíz                                                        |

## Uso de la API

Todos los endpoints bajo `/api/v1/` requieren la cabecera `X-API-Key` con uno de los tokens configurados en `API_KEYS`. `/docs`, `/openapi.json` y `/health` quedan públicos.

```bash
curl -H "X-API-Key: <tu-token>" \
  "http://localhost:8000/api/v1/products?postal_code=28001&term=leche"
```

Respuesta (`200`):

```json
{
  "search": {
    "postal_code": "28001",
    "term": "leche",
    "warehouse": "mad1",
    "strategy_used": "algolia",
    "scraped_at": "2026-09-21T10:00:00Z",
    "total_results": 1
  },
  "products": [
    {
      "id": "10381",
      "name": "Leche semidesnatada Hacendado",
      "price": 5.04,
      "price_format": "0.84 €/L",
      "image_url": "https://prod-mercadona.imgix.net/...",
      "category": "Huevos, leche y mantequilla"
    }
  ]
}
```

Sin `X-API-Key` (o con una inválida) → `401`. Si Mercadona/Algolia no responde tras agotar los reintentos → `502`.

## Docker

```bash
docker compose up -d
```

Levanta la API junto a un Redis local (`redis:7-alpine`) en una red interna — requiere un `.env` con `MERCADONA_BASE_URL`/`API_KEYS`/etc. (`REDIS_URL` se sobrescribe automáticamente para apuntar al servicio `redis` del compose, no hace falta configurarlo). El puerto de host es configurable vía `API_PORT` (`8000` por defecto).

Build/ejecución standalone:

```bash
docker build -t mercadona-scraper .
docker run -p 8000:8000 \
  -e MERCADONA_BASE_URL=https://tienda.mercadona.es \
  -e REDIS_URL=redis://<tu-redis>:6379/0 \
  mercadona-scraper
```

La imagen corre como usuario sin privilegios y expone un `HEALTHCHECK` contra `GET /health`.

## Tests y calidad

```bash
pytest -q                 # suite completa (nunca contra Mercadona real)
pytest --cov=app          # con cobertura
ruff check . && ruff format .
```

Los tests de integración usan `respx` para simular Mercadona/Algolia y `fakeredis` para Redis — ninguna ejecución de `pytest` toca la red real.

## Desarrollo dirigido por especificaciones (SDD)

Cada feature del proyecto sigue el mismo ciclo, documentado en `specs/<NNN>-<nombre>/`:

1. **`spec.md`** — requisitos funcionales en formato EARS, historias de usuario, casos límite, fuera de alcance
2. **`plan.md`** — módulos, modelo de datos, decisiones de diseño justificadas (con la alternativa descartada)
3. **`tasks.md`** — desglose en tareas <30 min, ordenadas por dependencia, con criterio "Hecho cuando" verificable
4. Implementación tarea a tarea, TDD estricto (test primero, en rojo, luego el código que lo pone en verde)

Specs completas:

| Spec | Contenido |
| ---- | --------- |
| `001-mercadona-scraper-mvp` | Búsqueda de productos, cache Redis, mapeo de datos |
| `002-mercadona-scraper-antibaneo` | Rotación de User-Agent, reintentos con backoff, respeto de `Retry-After` |
| `003-mercadona-scaper-logging` | Logging estructurado, correlación por request-id, exception handler global |
| `004-mercadona-scraper-authentication` | Autenticación por `X-API-Key` |
| `005-mercadona-scraper-dockerization` | Dockerfile, docker-compose, endpoint `/health` |
| `006-mercadona-scraper-refactor` | Cache de credenciales Algolia, providers de DI centralizados, tipado de `app.state` |

## Limitaciones conocidas

- **Resolución de almacén provisional:** todo `postal_code` resuelve al mismo almacén (`mad1`) — la resolución real código postal → almacén no está implementada (ver Decisión D8, `specs/001-mercadona-scraper-mvp/plan.md`).
- **Sin rotación de IP/proxy:** decisión explícita, fuera de alcance del proyecto (ver `specs/002-mercadona-scraper-antibaneo/spec.md`).
- **Cache de credenciales en memoria de proceso:** no se comparte entre réplicas si el servicio se despliega con más de una instancia; cada una vuelve a extraerlas tras un reinicio.
