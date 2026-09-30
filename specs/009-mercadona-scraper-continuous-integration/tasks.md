# Tasks 009 — Continuous Integration

Desglose de [plan.md](plan.md). Orden = orden de dependencia (§4 de plan.md). Cada tarea <30 min y es una unidad de trabajo revisable. Este spec no añade código de aplicación, así que no hay tests `pytest` nuevos: cada tarea se verifica con una comprobación que **primero falla (RED)** y luego pasa (GREEN), según la tabla de §3 de plan.md, y deja `pytest -q` completo en verde al cerrar.

## PR único — CI y versiones reproducibles

Rama `009-continuous-integration`, base `main`. Estimación: **≈80 líneas escritas a mano** + `uv.lock` generado (≈1050), plan.md §6.

- [x] **T1 — `uv.lock` y `.python-version`**
  **Hallazgo durante T1:** `uv run pytest` fallaba con `ModuleNotFoundError: No module named 'tests'` en 20 ficheros. El fallo existía desde la spec 004 también en el entorno local: el comando documentado (`pytest`) no funcionaba, solo `python -m pytest`, que añade el directorio actual a `sys.path`. Se arregla aquí con `pythonpath = ["."]` en `[tool.pytest.ini_options]`, porque la CI ejecuta `pytest` (RF-8); verificado con `uv run pytest`, `pytest` y `python -m pytest` (217 en los tres).
  Genera `uv.lock` con `uv lock` a partir del `pyproject.toml` actual y crea `.python-version` con `3.11` (D1, D2 de plan.md).
  RED: `uv sync --locked --extra dev` falla porque no existe `uv.lock`.
  GREEN: tras `uv lock`, `uv sync --locked --extra dev` instala en Python 3.11; `uv run python -c "import fastapi, starlette; print(fastapi.__version__, starlette.__version__)"` muestra `0.142.2 1.7.0` (RF-5); `uv run pytest -q` pasa (217); `uv run ruff check .` y `uv run ruff format --check .` limpios. Prueba negativa de RF-2 en local: añadir temporalmente una dependencia a `pyproject.toml` ⇒ `uv sync --locked` sale con código 1; revertir el cambio y confirmar que `uv lock --check` vuelve a pasar.
  Depende: —.
  RF: RF-1, RF-2, RF-3, RF-5.
  Hecho cuando: `uv.lock` y `.python-version` existen, `uv lock --check` pasa y la suite está en verde en el entorno de `uv` (Python 3.11).

- [ ] **T2 — `pyproject.toml`: umbral de cobertura**
  Añade `[tool.coverage.report]` con `fail_under = 80` (D4).
  RED: con `fail_under = 100` temporal, `uv run pytest -q --cov=app` falla por cobertura (hoy 99%).
  GREEN: con `fail_under = 80`, pasa. `uv lock --check` sigue pasando (las secciones `[tool.*]` no afectan a la resolución).
  Depende: T1.
  RF: RF-9.
  Hecho cuando: el umbral está en `pyproject.toml`, `uv run pytest -q --cov=app` pasa y `uv lock --check` pasa.

- [ ] **T3 — `Dockerfile`: dependencias desde `uv.lock`**
  En la etapa `builder`: `COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/uv`, copia `pyproject.toml` y `uv.lock`, `uv export --locked --no-emit-project --format requirements-txt > requirements.txt`, `pip install --no-cache-dir -r requirements.txt` y `pip install --no-cache-dir --no-deps .` (D5). La etapa `runtime` no cambia.
  RED: la imagen actual, construida con `pip install .`, lleva otra versión de FastAPI que la del lock (comprobar con `docker run --rm <imagen> python -c "import fastapi; print(fastapi.__version__)"` antes del cambio).
  GREEN: `docker build -t mercadona-scraper:ci .` termina; la misma comprobación muestra `0.142.2`; `pytest` y `ruff` **no** están instalados en la imagen (`python -c "import pytest"` falla); un contenedor arrancado con `MERCADONA_BASE_URL` y `REDIS_URL` llega a estado `healthy` y `GET /health` responde `{"status": "ok"}`.
  Depende: T1.
  RF: RF-2, RF-4.
  Hecho cuando: la imagen se construye desde el lock, lleva las versiones del lock sin herramientas de desarrollo y pasa su `HEALTHCHECK`.

- [ ] **T4 — `.github/workflows/ci.yml`**
  Workflow con disparadores `push` a `main` y `pull_request` contra `main`; `permissions: contents: read`; `concurrency` por rama con `cancel-in-progress`; un job en `ubuntu-latest` con `actions/checkout@v7`, `astral-sh/setup-uv@v10` (`python-version: "3.11"`, caché activada), `uv sync --locked --extra dev`, y pasos separados `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest -q --cov=app` (D3).
  RED/GREEN: no se puede ejecutar GitHub Actions en local. Se verifica que el YAML es válido y que cada comando del job, ejecutado a mano en local con el entorno de `uv`, pasa en el mismo orden. La ejecución real en GitHub es T6.
  Depende: T2.
  RF: RF-6, RF-7, RF-8, RF-10.
  Hecho cuando: el fichero existe, es YAML válido, y los cuatro comandos del job pasan en local en ese orden.

- [ ] **T5 — Docs vivas: `README.md`**
  Badge de estado del workflow (`https://github.com/serrano1996/mercadona-scraper/actions/workflows/ci.yml/badge.svg`) al principio; sección de entorno con `uv sync --locked --extra dev` como forma recomendada de reproducir la CI (y el aviso de que usa Python 3.11 por `.python-version`); cómo actualizar dependencias (`uv lock --upgrade` o editar `pyproject.toml` + `uv lock`); nota de que `pytest --cov` aplica el umbral del 80% de `pyproject.toml`; paso manual para proteger `main` en GitHub (Settings → Branches → exigir el check de CI antes de fusionar).
  Depende: T4.
  RF: RF-3, RF-9, RF-11; constitución #9/#10.
  Hecho cuando: el README recoge los cinco puntos y `ruff check .` y `ruff format --check .` siguen limpios.

- [ ] **T6 — Verificación en GitHub** (requiere autorización del usuario para subir la rama y abrir PRs)
  Subir la rama `009-continuous-integration` y abrir el PR contra `main`.
  Comprobaciones: la CI se ejecuta en el PR y termina en verde con Python 3.11 (RF-6, RF-7, RF-8, RF-10); un commit temporal con un test roto la pone en rojo en el paso de `pytest` y el fallo se ve en el PR (RF-8); un commit temporal que añade una dependencia a `pyproject.toml` sin regenerar el lock la pone en rojo en el paso de `uv sync` (RF-2). Ambos commits temporales se revierten antes de fusionar. Tras fusionar, el `push` a `main` ejecuta la CI en verde y el badge del README muestra el estado (RF-11).
  Depende: T5.
  RF: RF-2, RF-6, RF-7, RF-8, RF-10, RF-11; criterios de finalización de spec.md.
  Hecho cuando: las tres ejecuciones del PR dan el resultado esperado (verde, rojo por test, rojo por lock), la CI de `main` está en verde tras fusionar y el badge lo refleja.

## Trazabilidad RF → tareas

| RF | Descripción (resumen) | Tareas |
|---|---|---|
| RF-1 | Lockfile versionado con todas las dependencias exactas | T1 |
| RF-2 | Lockfile desfasado ⇒ CI (y build de Docker) fallan | T1, T3, T6 |
| RF-3 | Reproducir el entorno de CI en local con un comando | T1, T5 |
| RF-4 | La imagen Docker instala producción desde el mismo lockfile | T3 |
| RF-5 | Lockfile inicial con las últimas versiones compatibles (`fastapi 0.142.2`) | T1 |
| RF-6 | CI en `push` a `main` y en PRs contra `main` | T4, T6 |
| RF-7 | Solo Python 3.11, dependencias solo desde el lockfile | T4, T6 |
| RF-8 | `ruff check`, `ruff format --check` y `pytest` con cobertura; cualquier fallo ⇒ rojo | T4, T6 |
| RF-9 | Cobertura de `app/` < 80% ⇒ rojo | T2, T5 |
| RF-10 | Sin secretos ni servicios externos, permisos de solo lectura | T4, T6 |
| RF-11 | Resultado visible en GitHub y badge en el README | T5, T6 |

Todos los RF-1 a RF-11 quedan cubiertos por al menos una tarea; ninguno queda sin mapear.
