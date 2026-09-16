# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This repo is currently an empty scaffold: only [agents.md](agents.md) and SDD tooling metadata under [.atl/](.atl) exist. There is no `app/` source tree, no `pyproject.toml`/`requirements.txt`, no tests, and no `docs/` directory yet — the commands and structure below are the intended contract from `agents.md`, not verified working commands. Before relying on them, check whether the project has since been scaffolded (`ls app/`, `pyproject.toml`).

## Project

Async REST API built with Python and FastAPI that scrapes, processes, and serves Mercadona product data. It calls Mercadona's internal/undocumented endpoints (via `httpx`), validates and transforms data with Pydantic, and caches results with Redis to minimize unnecessary requests.

## Commands

- **Run:** `uvicorn app.main:app --reload`
- **Tests:** `pytest`
- **Lint/format:** `ruff check . && ruff format .`

After any task, run `ruff check .` and `pytest`, and confirm Swagger docs (`/docs`) load and show updated schemas.

## Architecture

Modular, FastAPI-oriented layout (once scaffolded):
- `app/api/` — route handlers
- `app/services/` — business logic
- `app/models/` — Pydantic schemas
- `app/scrapers/` — Mercadona endpoint clients

## Conventions

- Python 3.11+ with explicit type hints; no `Any` in type annotations.
- Code, docstrings, and commit messages in English; technical documentation in Spanish.
- Naming: `snake_case` for functions/variables/files/modules, `PascalCase` for classes and Pydantic models, `UPPER_SNAKE_CASE` for constants/env vars.
- All endpoints and external calls must be async (`async def`, `httpx.AsyncClient`).
- All I/O must be validated with **Pydantic v2** schemas.
- Do not add Playwright, Selenium, or BeautifulSoup without discussion — prefer consuming Mercadona's internal JSON endpoints directly.
- Read [docs/constitution.md](docs/constitution.md) and the active spec before changing code.
