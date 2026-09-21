# Tasks 005 — Dockerization

Desglose de [plan.md](plan.md). Orden = orden de dependencia. Cada tarea <30 min.

Nota (plan.md sección 5): la mayoría de estas tareas son de infraestructura, verificables sólo manualmente (`pytest` no construye imágenes Docker) — sólo T1 tiene TDD real con `pytest`.

- [x] **T1 — `main.py`: `GET /health`**
  `@app.get("/health")` junto al exception handler global — sin dependencias, responde `{"status": "ok"}` con `200`, sin tocar `Settings`/Redis/`MercadonaClient` (Decisión D1 en plan.md).
  Depende: —.
  RF: RF-9.
  Hecho cuando: test unitario en `tests/test_main.py` — `GET /health` sin `X-API-Key` → `200`, cuerpo `{"status": "ok"}`; `pytest -q` completo sigue en verde.

- [x] **T2 — `.dockerignore`**
  Excluye `.venv/`, `.git/`, `__pycache__/`, `tests/`, `specs/`, `docs/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`, `*.egg-info/`.
  Depende: —.
  RF: RF-8.
  Hecho cuando: el archivo existe con esas entradas; revisión manual de la lista contra `ls -a` del repo (no debe faltar ningún directorio pesado/irrelevante para el build).

- [x] **T3 — `Dockerfile`: stage `builder`**
  `FROM python:3.11-slim AS builder`; copia `pyproject.toml` (+ `app/` para que `pip install .` resuelva el paquete); `pip install --no-cache-dir .` (sólo `[project.dependencies]`, nunca el grupo `dev` — Decisión D3).
  Depende: —.
  RF: RF-2.
  Hecho cuando: `docker build --target builder .` completa sin error.

- [x] **T4 — `Dockerfile`: stage `runtime`**
  `FROM python:3.11-slim AS runtime`; copia los paquetes instalados del stage `builder` + `app/`; crea usuario `appuser` sin privilegios (Decisión D4), `chown` del `WORKDIR`, `USER appuser`; `HEALTHCHECK` vía `httpx` contra `/health` (Decisión D8); `CMD` con `uvicorn app.main:app --host 0.0.0.0 --port 8000`, sin `--reload` (Decisión D9).
  Depende: T1, T3.
  RF: RF-1, RF-3, RF-10.
  Hecho cuando: `docker build .` completa sin error; `docker run --rm <image> whoami` imprime `appuser`, no `root`.

- [x] **T5 — `docker-compose.yml`**
  Servicio `api` (`build: .`, `env_file: .env`, `environment: REDIS_URL=redis://redis:6379/0` — sobrescribe el `.env` local, Decisión D5 —, `ports: ["${API_PORT:-8000}:8000"]` — Decisión D7 —, `depends_on: redis`); servicio `redis` (`image: redis:7-alpine` — Decisión D6 —, sin puertos publicados al host salvo necesidad de debug).
  Depende: T2, T4.
  RF: RF-4, RF-5, RF-7.
  Hecho cuando: `docker compose config` valida el archivo sin error (sintaxis + interpolación de variables correctas).

- [x] **T6 — Verificación manual: imagen standalone responde**
  `docker build -t mercadona-scraper .` + `docker run` con las env vars obligatorias (`MERCADONA_BASE_URL`, `REDIS_URL` apuntando a un Redis accesible) — confirma `GET /docs` y `GET /health` responden `200` desde el host.
  Depende: T4.
  RF: RF-1, RF-9.
  Hecho cuando: ambas peticiones devuelven `200` contra el contenedor recién levantado.

- [x] **T7 — Verificación manual: fail-fast sin configuración obligatoria**
  `docker run` **sin** `MERCADONA_BASE_URL`/`REDIS_URL` — confirma que el contenedor termina (no queda "arriba" roto) y `docker logs` muestra el `ValidationError` de `Settings`.
  Depende: T4.
  RF: RF-6.
  Hecho cuando: el contenedor sale con código de error distinto de 0 y el log contiene el mensaje de validación de Pydantic.

- [x] **T8 — Verificación manual: `docker compose up` — networking API↔Redis**
  Alcance redefinido (ver commit): el host de Algolia está hardcodeado en `mercadona_client.py` (HTTPS, no configurable) — no es mockeable de forma limpia desde un contenedor separado sin tocar código fuera de alcance de esta spec o infraestructura TLS/DNS frágil, así que esta tarea verifica lo que RF-4/RF-5 realmente prueban: que el contenedor `api` resuelve y conecta al servicio `redis` por nombre (no `localhost`), no la lógica de scraping/Algolia (ya cubierta exhaustivamente en specs 001-004).
  Depende: T5.
  RF: RF-4, RF-5.
  Hecho cuando: `docker compose exec api` conecta y hace `PING` al Redis del compose (`redis://redis:6379/0`) con éxito, y `GET /health` responde `200` dentro del contenedor.

- [x] **T9 — Verificación manual: `HEALTHCHECK` refleja el estado real**
  Tras `docker compose up`, `docker compose ps` (o `docker ps`) muestra el contenedor `api` como `healthy` una vez pasa el `start-period`.
  Depende: T8.
  RF: RF-10.
  Hecho cuando: el estado `healthy` aparece en la salida del comando.

- [x] **T10 — Verificación manual: `.dockerignore` excluye lo esperado**
  Inspecciona la imagen resultante (`docker run --rm <image> ls -la /app` o `docker history`) y confirma que `tests/`, `.venv/`, `.git/`, `specs/`, `docs/` no están presentes.
  Depende: T4, T2.
  RF: RF-8.
  Hecho cuando: ninguno de esos directorios aparece dentro de la imagen.

- [ ] **T11 — Lint, format y cobertura**
  `ruff check . && ruff format .` limpio (sólo se tocó `main.py` en código Python); `pytest --cov=app` ≥80% sobre el código nuevo/modificado (mismo criterio que T10/T12 de specs 001-004).
  Depende: T1–T10.
  RF: NFR de calidad (constitución #7, #8).
  Hecho cuando: ambos comandos terminan sin error y el reporte de cobertura no baja del 80%.
