# Mercadona Scraper API

[![CI](https://github.com/serrano1996/mercadona-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/serrano1996/mercadona-scraper/actions/workflows/ci.yml)

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
- [Integración continua](#integración-continua)
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

- [`uv`](https://docs.astral.sh/uv/) (recomendado): instala Python 3.11 y las versiones exactas de `uv.lock`
- O bien Python 3.11 o superior con `pip` (sin garantía de versiones exactas)
- Redis accesible (local, contenedor, o gestionado) — no necesario si solo vas a correr los tests (usan `fakeredis`)
- Docker + Docker Compose (opcional, para ejecución containerizada)

## Instalación y ejecución local

Con `uv` (recomendado — mismo entorno que la CI y la imagen Docker):

```bash
uv sync --locked --extra dev     # Python 3.11 (.python-version) + versiones exactas de uv.lock

cp .env.example .env             # y rellena los valores (ver siguiente sección)

uv run uvicorn app.main:app --reload
```

Con `pip` (funciona, pero resuelve las últimas versiones compatibles en lugar de las de `uv.lock`):

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
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
| `WAREHOUSE_CACHE_TTL_SECONDS` | No    | `86400`  | TTL de la resolución `postal_code → almacén` en cache                        |
| `WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS` | No | `3600` | TTL de un `postal_code` cacheado como "sin servicio" (404 de Mercadona)      |
| `REDIS_TIMEOUT_SECONDS` | No | `1.0` | Tiempo límite (s) para conectar con Redis y para cada operación; si se supera, se sigue sin cache |
| `HTTP_TIMEOUT_SECONDS` | No | `5.0` | Tiempo límite (s) de cada petición a Mercadona/Algolia (conexión, lectura, escritura) |
| `RETRY_MAX_ATTEMPTS`    |     No      | `3`      | Intentos máximos por petición saliente a Mercadona/Algolia                   |
| `RETRY_BASE_DELAY`      |     No      | `0.5`    | Delay base (segundos) del backoff exponencial entre reintentos               |
| `RETRY_JITTER_MAX_S`    |     No      | `0.3`    | Jitter aleatorio máximo (segundos) añadido a cada delay de reintento         |
| `LOG_LEVEL`             |     No      | `INFO`   | Nivel de logging raíz                                                        |

## Uso de la API

Todos los endpoints bajo `/api/v1/` requieren la cabecera `X-API-Key` con uno de los tokens configurados en `API_KEYS`. `/docs`, `/openapi.json`, `/health` y `/ready` quedan públicos.

### `/health` y `/ready`

| Endpoint | Pregunta que responde | Respuesta |
| -------- | --------------------- | --------- |
| `GET /health` | ¿Está vivo el proceso? No comprueba dependencias. | Siempre `200 {"status": "ok"}` |
| `GET /ready` | ¿Puede esta instancia usar Redis? Hace `PING` con el tiempo límite de `REDIS_TIMEOUT_SECONDS`. | `200 {"status": "ready"}`, o `503 {"status": "unavailable", "redis": "unreachable"}` |

El `HEALTHCHECK` de Docker usa `/health`: un Redis caído no debe hacer que se reinicie un proceso sano, porque la API sigue funcionando sin cache. `/ready` sirve para saber si la instancia está sirviendo con cache. No comprueba Mercadona: una caída de un tercero marcaría a la vez todas las instancias como no listas. La respuesta `503` nunca incluye la URL de Redis ni el detalle del error (una URL de Upstash lleva la contraseña).

```bash
curl -H "X-API-Key: <tu-token>" \
  "http://localhost:8000/api/v1/products?postal_code=46001&term=leche"
```

`postal_code` se resuelve a su almacén Mercadona real (`change-pc` de Mercadona, cacheado — ver `specs/007-mercadona-scraper-warehouse-resolution/`), no a un valor fijo: precios y catálogo varían según el almacén.

`term` se normaliza antes de buscar: se quitan los espacios de los extremos, los espacios internos repetidos se reducen a uno y se pasa a minúsculas (`"  Leche   ENTERA "` → `"leche entera"`). La respuesta devuelve el término normalizado en `search.term`. Motivo: el buscador de Mercadona ignora mayúsculas y espacios internos pero no los de los extremos, así que normalizar nunca empeora el resultado y permite que búsquedas equivalentes compartan cache (ver `specs/008-mercadona-scraper-search-completeness/`).

Los resultados se paginan con dos parámetros opcionales:

| Parámetro | Default | Rango | Descripción |
| --------- | ------- | ----- | ----------- |
| `page` | `1` | ≥ 1 | Página a devolver (la primera es `1`) |
| `page_size` | `50` | 1-100 | Productos por página |

Sin ellos se devuelve la primera página de 50, como antes. `search.total_results` es el **total real** de productos que coinciden con la búsqueda, no los de la página; para recorrerlos todos, pide `page` desde `1` hasta `search.total_pages`:

```bash
curl -H "X-API-Key: <tu-token>" \
  "http://localhost:8000/api/v1/products?postal_code=46001&term=leche&page=2&page_size=50"
```

El buscador de Mercadona solo deja paginar los primeros 1000 resultados. En búsquedas muy amplias `total_pages × page_size` puede ser menor que `total_results`: los productos que quedan más allá no son accesibles.

Respuesta (`200`):

```json
{
  "search": {
    "postal_code": "46001",
    "term": "leche",
    "warehouse": "vlc1",
    "strategy_used": "algolia",
    "scraped_at": "2026-09-21T10:00:00Z",
    "total_results": 233,
    "page": 1,
    "page_size": 50,
    "total_pages": 5
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

(Se muestra un solo producto; la respuesta real trae hasta `page_size`.)

Sin `X-API-Key` (o con una inválida) → `401`. `postal_code` con formato inválido (≠ 5 dígitos) → `422`. `term` vacío, de solo espacios o de más de 100 caracteres tras normalizar → `422` (un término vacío devolvería el catálogo entero). `page` < 1 o `page_size` fuera de 1-100 → `422`. `postal_code` fuera de la zona de servicio de Mercadona → `404` (`"Postal code not served by Mercadona"`). `page` más allá de la última página → `404` (`"Page out of range"`). Si Mercadona/Algolia no responde tras agotar los reintentos → `502`.

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

La imagen corre como usuario sin privilegios y expone un `HEALTHCHECK` contra `GET /health`. Sus dependencias se instalan desde `uv.lock`, así que lleva exactamente las versiones que prueba la CI; si `uv.lock` no está sincronizado con `pyproject.toml`, el build falla.

## Tests y calidad

```bash
uv run pytest -q                 # suite completa (nunca contra Mercadona real)
uv run pytest --cov=app          # con cobertura; falla por debajo del 80%
uv run ruff check . && uv run ruff format .
```

(Sin `uv`, los mismos comandos sin el prefijo `uv run`.) El umbral de cobertura del 80% está en `pyproject.toml` y se aplica siempre que se use `--cov`: si ejecutas un solo fichero de tests **con** `--cov`, fallará por cobertura total baja; sin `--cov` no afecta.

Los tests de integración usan `respx` para simular Mercadona/Algolia y `fakeredis` para Redis — ninguna ejecución de `pytest` toca la red real.

## Integración continua

Cada `push` a `main` y cada PR contra `main` ejecutan [`.github/workflows/ci.yml`](.github/workflows/ci.yml) en GitHub Actions, con **Python 3.11** (la misma versión que la imagen Docker) y las dependencias instaladas **solo desde `uv.lock`**:

1. `uv sync --locked --extra dev` — falla si `uv.lock` no está sincronizado con `pyproject.toml`
2. `ruff check .`
3. `ruff format --check .`
4. `pytest -q --cov=app` — falla si algún test falla o la cobertura baja del 80%

No necesita secretos ni servicios externos, y tiene permisos de solo lectura sobre el repositorio. El resultado aparece junto a cada commit y PR, y en el badge de arriba.

**Reproducir la CI en local:** `uv sync --locked --extra dev` y los tres comandos de la sección anterior.

**Actualizar dependencias:** edita `pyproject.toml` y ejecuta `uv lock` (o `uv lock --upgrade` para subir todo a las últimas versiones compatibles), y commitea `uv.lock` junto al cambio. La CI confirma en el PR que la suite sigue pasando con las versiones nuevas.

**Proteger `main` (paso manual en GitHub):** *Settings → Branches → Add branch protection rule* para `main`, marca *Require status checks to pass before merging* y selecciona el check `test` del workflow `CI`. Así no se puede fusionar un PR con la CI en rojo. La CI solo prueba el último commit de cada `push`: un commit intermedio en rojo dentro de un PR con varios commits no se detecta por separado.

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
| `007-mercadona-scraper-warehouse-resolution` | Resolución real `postal_code → almacén` vía Mercadona, cache Redis con TTL propio, clave de cache de productos por almacén |
| `008-mercadona-scraper-search-completeness` | Total real de resultados, paginación (`page`, `page_size`), validación y normalización del término |
| `009-mercadona-scraper-continuous-integration` | CI en GitHub Actions con Python 3.11, `uv.lock` compartido con la imagen Docker, umbral de cobertura del 80% |
| `010-mercadona-scraper-operational-robustness` | Tiempos límite configurables de Redis y HTTP, degradación sin cache ante un Redis que no responde, endpoint `/ready` |

## Limitaciones conocidas

- **Sin rotación de IP/proxy:** decisión explícita, fuera de alcance del proyecto (ver `specs/002-mercadona-scraper-antibaneo/spec.md`).
- **Latencia añadida con Redis colgado:** si Redis acepta la conexión pero no responde, cada búsqueda hace hasta cuatro operaciones de cache que esperan `REDIS_TIMEOUT_SECONDS` cada una antes de seguir sin cache, así que puede tardar hasta unas cuatro veces ese valor más la llamada a Mercadona (unos 4 s con el valor por defecto). No hay *circuit breaker* que deje de intentarlo tras varios fallos (ver `specs/010-mercadona-scraper-operational-robustness/spec.md`).
- **Cache de credenciales en memoria de proceso:** no se comparte entre réplicas si el servicio se despliega con más de una instancia; cada una vuelve a extraerlas tras un reinicio.
