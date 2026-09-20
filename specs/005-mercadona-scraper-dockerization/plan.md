# Plan 005 — Dockerization

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código: define módulos, decisiones de diseño y estrategia de test. Numeración de decisiones (D1..) propia de este plan.

## 1. Módulos

```
Dockerfile              # NUEVO: build multi-stage, imagen final sin herramientas de build, usuario no-root
docker-compose.yml       # NUEVO: servicio `api` + servicio `redis` (redis:7-alpine), red interna
.dockerignore            # NUEVO: excluye .venv/, .git/, tests/, specs/, docs/, caches, .coverage
app/
└── main.py              # MODIFICADO: + GET /health (sin auth, sin tocar Redis/Mercadona)
```

`app/api/v1/products.py`, `app/core/*`, `app/scrapers/*`, etc. **no cambian** — toda la dockerización es infraestructura nueva; el único cambio en código Python es la ruta `/health` (RF-9), que vive junto al exception handler global en `main.py`, no en un router aparte.

Cobertura por RF:
- `Dockerfile` → **RF-1, RF-2, RF-3, RF-10**
- `docker-compose.yml` → **RF-4, RF-5, RF-7**
- `.dockerignore` → **RF-8**
- `main.py` (`GET /health`) → **RF-9**
- `Settings` (ya existente, sin cambios) → soporte de **RF-5, RF-6**

## 2. Modelo de datos

Ninguno nuevo. `/health` devuelve un JSON mínimo sin schema Pydantic dedicado (`{"status": "ok"}`) — no hay entrada que validar y la salida no se referencia desde ningún cliente más allá del propio `HEALTHCHECK`.

## 3. Decisiones de diseño

### D1 — `/health` inline en `main.py`, no un router/módulo aparte
**Elegido:** `@app.get("/health")` definido directamente en `main.py`, junto al exception handler global — sin dependencias, sin tocar `Settings`/Redis/`MercadonaClient`.
**Descartado:** un módulo `app/api/health.py` con su propio `APIRouter`. Motivo del rechazo: sobre-ingeniería para una única ruta trivial sin lógica ni dependencias propias; además, definirla fuera de `app.include_router(products_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])` dentro del propio `main.py` deja visualmente claro que queda fuera del alcance de `verify_api_key` **por construcción** (misma razón por la que `/docs`/`/openapi.json` ya quedan fuera), no por una excepción añadida al propio `verify_api_key`.
RF: **RF-9**.

### D2 — Build multi-stage, no single-stage
**Elegido:** dos stages en el `Dockerfile` — `builder` (instala dependencias con `pip install .` sobre `python:3.11-slim`) y `runtime` (copia sólo los paquetes instalados + `app/` a una imagen `python:3.11-slim` limpia, sin cache de pip ni herramientas de build).
**Descartado:** un único stage que instale dependencias y copie el código en la misma capa. Motivo del rechazo: RF-2 exige minimizar el tamaño final — un stage único arrastra cache de `pip`, metadatos de build y (si alguna dependencia futura compilara extensiones C) herramientas de compilación a la imagen que se despliega, aumentando tamaño y superficie de ataque sin ningún beneficio.
RF: **RF-2**.

### D3 — Dependencias de producción vía `pip install .` sobre `pyproject.toml`, sin `requirements.txt` aparte
**Elegido:** `pip install --no-cache-dir .` instala el proyecto y sólo `[project.dependencies]` (fastapi, pydantic, pydantic-settings, httpx, redis, uvicorn) — el grupo `dev` (`pytest`, `ruff`, `respx`, `fakeredis`) vive en `[project.optional-dependencies].dev` y nunca se instala salvo que se pida explícitamente (`pip install .[dev]`).
**Descartado:** mantener un `requirements.txt`/`requirements-prod.txt` generado o escrito a mano en paralelo a `pyproject.toml`. Motivo del rechazo: duplica la fuente de verdad de las dependencias — riesgo real de que diverjan (una dependencia añadida a `pyproject.toml` pero olvidada en `requirements.txt`), sin ningún beneficio ya que `pyproject.toml` ya separa prod/dev correctamente.
RF: **RF-2**.

### D4 — Usuario no-root dedicado, creado en el stage `runtime`
**Elegido:** `useradd --create-home --shell /usr/sbin/nologin appuser` en el stage `runtime`, `chown` del `WORKDIR` a ese usuario, y `USER appuser` antes del `CMD`.
**Descartado:** ejecutar como el usuario `nobody` ya presente en la imagen base, o mantener `root` y confiar en que el orquestador de despliegue restrinja privilegios. Motivo del rechazo: `nobody` no tiene `HOME` ni permisos de escritura predecibles en `python:3.11-slim` (puede romper cosas que esperen un `$HOME` válido); confiar en el orquestador no cumple RF-3, que pide que el propio contenedor no ejecute como root independientemente de dónde se despliegue.
RF: **RF-3**.

### D5 — `docker-compose.yml` fuerza `REDIS_URL` del servicio Redis vía `environment:`, el resto de config viene de `env_file: .env`
**Elegido:** el servicio `api` del compose usa `env_file: .env` (reutiliza el mismo `.env` que el desarrollo local ya usa para `MERCADONA_BASE_URL`, `API_KEYS`, `LOG_LEVEL`, etc.) pero además fija `environment: REDIS_URL=redis://redis:6379/0` — en Docker Compose, `environment:` tiene prioridad sobre `env_file:` para la misma clave, así que esto sobrescribe cualquier `REDIS_URL=redis://localhost:6379/0` que el `.env` tenga para uso local no dockerizado.
**Descartado:** mantener un `.env.docker` separado con todas las variables duplicadas. Motivo del rechazo: duplica configuración que sólo difiere en una clave (`REDIS_URL`, porque `localhost` no resuelve al contenedor de Redis desde dentro de otro contenedor) — dos archivos a mantener sincronizados para N-1 variables idénticas es más frágil que sobrescribir la única que realmente cambia.
RF: **RF-4, RF-5**.

### D6 — Redis oficial `redis:7-alpine`, versión fijada (no `latest`)
**Elegido:** `image: redis:7-alpine` en el servicio `redis` del compose.
**Descartado:** `redis:latest`. Motivo del rechazo: `latest` no es reproducible entre builds — un bump de versión mayor de Redis podría cambiar comportamiento (ej. defaults de persistencia) sin que nada en el repo lo refleje. Fijar la major (`7`) da estabilidad sin atarse a un patch exacto que habría que actualizar manualmente por cada fix de seguridad.
RF: **RF-4**.

### D7 — Puerto configurable vía variable de entorno con default, no hardcodeado
**Elegido:** `ports: ["${API_PORT:-8000}:8000"]` en el servicio `api` — el contenedor siempre escucha en `8000` internamente (fijo, es un detalle de implementación), pero el puerto del host es configurable vía `API_PORT` con `8000` como default si no se define.
**Descartado:** hardcodear `"8000:8000"` sin posibilidad de override. Motivo del rechazo: RF-7 exige explícitamente que el puerto sea configurable — sin la variable, dos instancias del proyecto en la misma máquina (o un puerto 8000 ya ocupado) no podrían convivir sin editar el propio `docker-compose.yml`.
RF: **RF-7**.

### D8 — `HEALTHCHECK` vía Python/`httpx` (ya presente), no `curl`
**Elegido:** `HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"` en el `Dockerfile`.
**Descartado:** instalar `curl` (`apt-get install -y curl`) sólo para el `HEALTHCHECK`. Motivo del rechazo: `httpx` ya es una dependencia de producción del proyecto (RF-2 la instala igualmente) — añadir `curl` sólo para esto infla la imagen y el `apt-get` con un paquete cuyo único uso es una comprobación que `httpx` ya resuelve.
RF: **RF-10**.

### D9 — Sin `--reload` en el `CMD` de la imagen
**Elegido:** `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` — sin `--reload`.
**Descartado:** habilitar `--reload` (requeriría además montar el código fuente como volumen en el compose, para que el reload tenga algo que vigilar). Motivo del rechazo: spec.md encuadra esto como empaquetado (H1: "construir y levantar... para probarla"), no como un bucle de desarrollo con hot-reload — eso ya lo cubre `uvicorn --reload` fuera de Docker (comando ya documentado en `CLAUDE.md`/`agents.md`). Añadirlo aquí mezclaría una imagen de "ejecución" con una de "desarrollo", ampliando el alcance sin que spec.md lo pidiera.
RF: soporte de **RF-1** (mantiene la imagen enfocada en ejecución, no en desarrollo).

## 4. Estrategia de test

**Unitario — `GET /health`** (extiende `tests/test_main.py`, mismo patrón que `test_docs_and_openapi_stay_public_without_api_key`)
- `GET /health` sin `X-API-Key` → `200`, cuerpo `{"status": "ok"}`.
- No se mockea ni se toca `CacheRepository`/`MercadonaClient` — se puede llamar sin `dependency_overrides` porque la ruta no declara ninguna dependencia de negocio (verificable por construcción: la función de la ruta no recibe parámetros).

**Verificación de infraestructura (no `pytest` — comandos manuales, documentados en tasks.md)**
- `docker build .` completa sin error.
- Imagen resultante: `docker run` + `curl`/`httpx` contra `/docs` y `/health` desde el host → ambos `200`.
- `docker compose up`: `GET /api/v1/products` con token válido, contra upstream simulado (respx no aplica aquí — se simula manualmente con un stub, mismo criterio de "nunca contra Mercadona real" que T13 de specs 002/003/004).
- `docker compose ps` tras el arranque: contenedor `api` en estado `healthy` (confirma D8).
- Tamaño/contenido de la imagen (`docker history` o `docker run ... ls`): confirma que `tests/`, `.venv/`, `.git/` no están presentes (RF-8).
- `docker run` sin `MERCADONA_BASE_URL`/`REDIS_URL` → el contenedor termina con el `ValidationError` de `Settings` visible en `docker logs` (RF-6), no queda "arriba" en un estado roto.

**Cobertura:** el único código Python nuevo es la ruta `/health` (unas pocas líneas) — cobertura ≥80% del código nuevo/modificado se cumple trivialmente con el test unitario de arriba; no aplica a los archivos de infraestructura (`Dockerfile`/`docker-compose.yml`/`.dockerignore` no son código Python, no los mide `pytest --cov`).

## 5. Nota sobre alcance de la verificación manual

A diferencia de specs anteriores (donde "verificación manual" era el último paso sobre código ya cubierto por tests automatizados), aquí gran parte de los criterios de finalización de spec.md (build, `docker compose up`, `HEALTHCHECK`, tamaño de imagen) **sólo son verificables manualmente** — no hay forma razonable de que `pytest` construya imágenes Docker. Las tareas de `tasks.md` deben reflejar esto explícitamente: la mayoría de RF de infraestructura se marcan "hecho" por verificación manual documentada, no por un test en verde.
