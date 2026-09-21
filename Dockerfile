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
