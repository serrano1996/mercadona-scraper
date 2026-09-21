# syntax=docker/dockerfile:1

# ---- builder ----
# T3 — 005-mercadona-scraper-dockerization: installs only production
# dependencies via `pip install .` directly from pyproject.toml — the
# [project.optional-dependencies].dev group (pytest, ruff, respx,
# fakeredis) is never installed here (plan.md Decision D3).
FROM python:3.11-slim AS builder

WORKDIR /app

COPY pyproject.toml ./
COPY app/ ./app/

RUN pip install --no-cache-dir .

# ---- runtime ----
# T4 — copies only the installed dependencies + app/ source from
# `builder` (never pip caches, build tools, or pyproject.toml itself);
# runs as a dedicated non-root user (plan.md Decision D4); HEALTHCHECK
# uses httpx — already a prod dependency — instead of installing curl
# just for this (Decision D8); no --reload in CMD, this image is for
# running the app, not for a hot-reload dev loop (Decision D9).
FROM python:3.11-slim AS runtime

RUN useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser app/ ./app/

USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
