# Plan 009 — Continuous Integration

Basado en [constitution.md](../../docs/constitution.md) y [spec.md](spec.md). Sin código de aplicación: define ficheros, decisiones y verificación. Numeración de decisiones (D1..) propia de este plan. spec.md no tiene dudas abiertas.

**Hechos verificados el 2026-09-30** en una copia aislada del proyecto (sin tocar el repositorio), con `uv 0.12.10`:
- `uv lock` resuelve este `pyproject.toml` (build backend `setuptools`, extra `dev`) sin cambios: `fastapi 0.142.2`, `starlette 1.7.0`, `pydantic 2.13.5`.
- `uv sync --locked --extra dev` instala en Python 3.11.16. Tras añadir una dependencia a `pyproject.toml` sin regenerar el lock, `uv sync --locked` y `uv lock --check` **salen con código 1** ("To update the lockfile, run `uv lock`").
- `uv export --locked --no-emit-project --format requirements-txt` exporta solo producción (sin `pytest`, `ruff`, `respx`).
- La suite pasa en Python 3.11 con esas versiones (217 tests; `ruff check` y `ruff format --check` limpios).
- Últimas versiones: `actions/checkout` v7.0.1, `astral-sh/setup-uv` v10.2.0. Docker 29.6.2 disponible en local.

## 1. Ficheros

```
.github/workflows/ci.yml   # NUEVO: workflow de GitHub Actions
uv.lock                    # NUEVO (generado): versiones exactas, producción + extra dev
.python-version            # NUEVO: "3.11"
pyproject.toml             # MODIFICADO: [tool.coverage.report] fail_under = 80
Dockerfile                 # MODIFICADO: etapa builder instala desde uv.lock
README.md                  # MODIFICADO: badge de CI, entorno con uv, protección de rama
```

Nada en `app/` ni en `tests/` cambia.

Cobertura por RF:
- `uv.lock` → **RF-1, RF-5**; `uv.lock` + `--locked` en CI y Docker → **RF-2**
- `.python-version` + README → **RF-3**
- `Dockerfile` → **RF-4**
- `ci.yml` → **RF-6, RF-7, RF-8, RF-10**; `pyproject.toml` → **RF-9**
- README (badge) + GitHub → **RF-11**

## 2. Decisiones de diseño

### D1 — `uv` como gestor del lockfile
**Elegido:** `uv` (ya instalado, 0.12.10), con `uv.lock` versionado. Resuelve producción y extras en un solo fichero multiplataforma, falla solo con `--locked` si el lock está desfasado (RF-2, verificado), instala Python 3.11 bajo demanda (RF-3) y tiene acción oficial para GitHub Actions.
**Descartado (`pip-tools`, `requirements*.txt` compilados):** un fichero por conjunto (prod, dev), y detectar que están desfasados exige un paso extra (`pip-compile` + `git diff --exit-code`).
**Descartado (Poetry):** obliga a migrar `pyproject.toml` a su formato o a su backend; `uv` trabaja con el `[project]` estándar actual sin cambios.
RF: **RF-1, RF-2, RF-3, RF-5**.

### D2 — `.python-version` con `3.11` en el repositorio
**Elegido:** fijar `3.11` para que `uv sync` en local cree el mismo entorno que la CI y la imagen Docker (H3). `uv` descarga 3.11 si no está.
**Coste asumido:** el entorno local habitual pasa de 3.14 a 3.11 cuando se usa `uv`. El flujo actual con `pip install -e ".[dev]"` sigue funcionando, pero sin garantías de versiones; el README recomienda `uv sync`.
RF: **RF-3, RF-7**.

### D3 — Workflow único, un job, `uv` + `--locked`
**Elegido:** `.github/workflows/ci.yml` con un único job en `ubuntu-latest`:
1. `actions/checkout@v7`.
2. `astral-sh/setup-uv@v10` con `python-version: "3.11"` y caché de `uv` activada.
3. `uv sync --locked --extra dev` (falla si el lock está desfasado, RF-2).
4. `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest -q --cov=app` (RF-8), en pasos separados para que GitHub muestre cuál falla.

Disparadores: `push` a `main` y `pull_request` contra `main` (RF-6). `permissions: contents: read` (RF-10). `concurrency` por rama con `cancel-in-progress` para no acumular ejecuciones de un PR que se actualiza varias veces.
**Descartado (matriz de versiones de Python):** fuera de alcance (spec.md, RF-7).
**Descartado (acciones fijadas por SHA en lugar de versión mayor):** más seguro frente a una etiqueta comprometida, pero exige actualizar SHAs a mano. Para un TFM se acepta la versión mayor (`@v7`, `@v10`); queda anotado como mejora.
RF: **RF-2, RF-6, RF-7, RF-8, RF-10**.

### D4 — Umbral de cobertura en `pyproject.toml`, no en la línea de comandos de la CI
**Elegido:** `[tool.coverage.report] fail_under = 80`. Local y CI aplican el mismo umbral desde un único sitio siempre que se ejecute con `--cov`.
**Descartado (`--cov-fail-under=80` solo en `ci.yml`):** el umbral viviría en dos sitios (CI y la costumbre de cada uno en local) y podría divergir.
**Coste asumido:** ejecutar en local un solo fichero de tests **con** `--cov` fallará por cobertura baja. Sin `--cov` no afecta; se documenta.
RF: **RF-9**.

### D5 — Docker: `uv export` en la etapa `builder`, `pip install` como hasta ahora
**Elegido:** en la etapa `builder` se copia el binario de `uv` desde su imagen oficial fijada (`COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/uv`), se copian `pyproject.toml` y `uv.lock`, y se ejecuta `uv export --locked --no-emit-project --format requirements-txt > requirements.txt`, `pip install --no-cache-dir -r requirements.txt` y `pip install --no-cache-dir --no-deps .`. La etapa `runtime` **no cambia**: sigue copiando `site-packages` y `bin` desde `builder`, usuario sin privilegios y `HEALTHCHECK` intactos (decisiones D3-D9 de plan.md 005).
Con `--locked`, construir la imagen con un lock desfasado falla igual que la CI (RF-2).
**Descartado (`uv sync` a un `.venv` y copiar el venv a `runtime`):** cambia la estructura de la imagen de la spec 005 (rutas, `PATH`) sin ganar nada frente a instalar las mismas versiones con `pip`.
**Descartado (commitear un `requirements.txt` exportado):** un segundo fichero de versiones que hay que acordarse de regenerar; exactamente la deriva que se quiere evitar.
RF: **RF-4**.

### D6 — Visibilidad y protección de rama
**Elegido:** badge de estado del workflow en `README.md` (`/actions/workflows/ci.yml/badge.svg`), que GitHub genera solo. La protección de rama (exigir CI en verde para fusionar) se documenta como paso manual en el README: es configuración de GitHub y la CLI `gh` no está instalada en este entorno.
RF: **RF-11**.

## 3. Estrategia de verificación

Este spec no añade código de aplicación, así que no hay tests `pytest` nuevos. Cada tarea se verifica con una comprobación que **primero falla** y luego pasa, que es el equivalente del ciclo RED/GREEN para infraestructura:

| RF | Comprobación | Rojo antes | Verde después |
|---|---|---|---|
| RF-1, RF-5 | `uv sync --locked --extra dev` en local | Falla: no hay `uv.lock` | Instala `fastapi 0.142.2` en Python 3.11 |
| RF-2 | Añadir una dependencia a `pyproject.toml` sin `uv lock`, luego `uv sync --locked` | — | Sale con código 1 (se revierte el cambio de prueba) |
| RF-3 | `uv sync --locked --extra dev && uv run pytest -q` desde cero | — | 217 tests en Python 3.11 |
| RF-9 | `uv run pytest -q --cov=app` con `fail_under = 100` temporal | Falla por cobertura (99%) | Con `fail_under = 80`, pasa |
| RF-4 | `docker build` + `docker run … python -c "import fastapi; print(fastapi.__version__)"` | La imagen actual lleva otra versión | `0.142.2`, y el contenedor llega a `healthy` |
| RF-6-RF-8, RF-10 | Subir la rama y abrir un PR | Sin CI | CI en verde en GitHub, con Python 3.11 |
| RF-8 (fallo) | Commit con un test roto a propósito en el PR | — | CI en rojo; se revierte el commit |
| RF-2 (en CI) | Commit con `pyproject.toml` modificado sin lock en el PR | — | CI en rojo en el paso de `uv sync`; se revierte |
| RF-11 | Badge en el README tras fusionar | — | Muestra el estado de `main` |

Las comprobaciones en GitHub (últimas tres filas) requieren **subir una rama y abrir un PR**, lo que publica código en el remoto: se piden al usuario en su momento, no se hacen por iniciativa propia.

## 4. Secuencia de implementación (base de tasks.md)

1. `uv.lock` + `.python-version`: generar el lock y comprobar `uv sync --locked` + suite en 3.11. Incluye la prueba negativa de RF-2 en local.
2. Umbral de cobertura en `pyproject.toml` (con la prueba del umbral al 100%). Regenera `uv.lock` si cambiar `pyproject.toml` lo requiere (no debería: `[tool.*]` no afecta a la resolución).
3. `Dockerfile` desde el lock; verificar versión dentro del contenedor y `HEALTHCHECK`.
4. `.github/workflows/ci.yml`.
5. README: entorno con `uv`, badge, nota del umbral de cobertura, paso manual de protección de rama.
6. Verificación en GitHub (con autorización del usuario): PR en verde, PR con test roto en rojo, PR con lock desfasado en rojo.

## 5. Riesgos y notas

- **Cambio del entorno local a 3.11 (D2):** si el desarrollador sigue usando su Python 3.14 con `pip`, puede volver a ver diferencias con la CI. El README deja `uv sync` como camino recomendado.
- **`uv.lock` es grande y generado:** no se revisa línea a línea; se revisa que `uv lock --check` pase y que las versiones clave sean las esperadas.
- **Aviso de obsolescencia de Starlette** (`TestClient` con `httpx`): con `starlette 1.7.0` fijado, aparece en cada ejecución. No falla la CI (no se usa `-W error`). Resolverlo queda fuera de alcance (spec.md).
- **Etiquetas de acciones por versión mayor (D3):** una etiqueta comprometida podría ejecutar código ajeno en la CI; el impacto está acotado por `permissions: contents: read` y la ausencia de secretos.
- **Los commits intermedios en rojo ya presentes en `main`** (p. ej. `bd537a8`) no se corrigen con este spec; la CI solo protege lo que se suba a partir de ahora.

## 6. Estimación de líneas cambiadas

| Bloque | Líneas (≈) |
|---|---|
| `ci.yml` | 40 |
| `Dockerfile` | 10 |
| `pyproject.toml`, `.python-version` | 4 |
| `README.md` | 25 |
| **Total escrito a mano** | **≈ 80** |
| `uv.lock` (generado, no se revisa línea a línea) | ≈ 1050 (medido en la prueba) |

Por debajo del presupuesto de 400 líneas revisables: **un único PR**.
