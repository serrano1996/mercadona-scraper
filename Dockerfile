# syntax=docker/dockerfile:1

# ---- builder ----
# T3 — 005-mercadona-scraper-dockerization: installs only production
# dependencies — the [project.optional-dependencies].dev group (pytest,
# ruff, respx, fakeredis) is never installed here (plan.md Decision D3).
# T3 — 009-mercadona-scraper-continuous-integration: the exact versions
# come from uv.lock, the same ones CI tests, instead of whatever
# `pip install .` resolves on build day (spec 009 RF-4, plan.md D5).
# --locked makes the build fail if uv.lock is out of sync with
# pyproject.toml (RF-2). uv is only used here; the runtime stage
# below never contains it.
FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY app/ ./app/

RUN uv export --locked --no-emit-project --format requirements-txt > requirements.txt \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

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
