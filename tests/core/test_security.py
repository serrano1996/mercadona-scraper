"""T2 — 004-mercadona-scraper-authentication: verify_api_key rejects a
missing or empty X-API-Key header with 401 (spec.md RF-2)."""

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import verify_api_key


@pytest.fixture
def settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        API_KEYS="valid-token",
    )


async def test_missing_header_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(api_key=None, settings=settings)

    assert exc_info.value.status_code == 401


async def test_empty_header_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await verify_api_key(api_key="", settings=settings)

    assert exc_info.value.status_code == 401


async def test_missing_and_empty_header_raise_same_detail(settings: Settings) -> None:
    with pytest.raises(HTTPException) as missing_exc:
        await verify_api_key(api_key=None, settings=settings)
    with pytest.raises(HTTPException) as empty_exc:
        await verify_api_key(api_key="", settings=settings)

    assert missing_exc.value.detail == empty_exc.value.detail
