"""Centralized FastAPI dependency providers reading from app.state
(spec 006-mercadona-scraper-refactor) — replaces the get_settings
duplicated between app/api/v1/products.py and app/core/security.py
(plan.md Decision D3), and gives every provider a typed view of
app.state via AppState + typing.cast (Decision D4). Zero behavior
change: same objects, same app.state, only centralized and typed.
"""

from typing import cast

from fastapi import Request

from app.core.config import Settings
from app.core.state import AppState
from app.scrapers.mercadona_client import MercadonaClient
from app.services.cache import CacheRepository


def _state(request: Request) -> AppState:
    return cast(AppState, request.app.state)


def get_settings(request: Request) -> Settings:
    return _state(request).settings


def get_cache_repository(request: Request) -> CacheRepository:
    return _state(request).cache_repository


def get_mercadona_client(request: Request) -> MercadonaClient:
    return _state(request).mercadona_client
