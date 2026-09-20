"""T2 — 004-mercadona-scraper-authentication: verify_api_key rejects a
missing or empty X-API-Key header with 401 (spec.md RF-2).

Extended for T3: token comparison against settings.api_keys, constant-time
via secrets.compare_digest (spec.md RF-1/RF-3/RF-4)."""

import pytest
from fastapi import HTTPException

from app.core import security
from app.core.config import Settings
from app.core.security import verify_api_key


@pytest.fixture
def settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        API_KEYS="valid-token",
    )


@pytest.fixture
def multi_token_settings() -> Settings:
    return Settings(
        MERCADONA_BASE_URL="https://tienda.mercadona.es",
        REDIS_URL="redis://localhost:6379/0",
        API_KEYS="app1-token,app2-token,app3-token",
    )


def test_missing_header_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(api_key=None, settings=settings)

    assert exc_info.value.status_code == 401


def test_empty_header_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(api_key="", settings=settings)

    assert exc_info.value.status_code == 401


def test_missing_and_empty_header_raise_same_detail(settings: Settings) -> None:
    with pytest.raises(HTTPException) as missing_exc:
        verify_api_key(api_key=None, settings=settings)
    with pytest.raises(HTTPException) as empty_exc:
        verify_api_key(api_key="", settings=settings)

    assert missing_exc.value.detail == empty_exc.value.detail


def test_invalid_token_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(api_key="not-the-right-token", settings=settings)

    assert exc_info.value.status_code == 401


def test_invalid_token_raises_same_detail_as_missing_header(settings: Settings) -> None:
    with pytest.raises(HTTPException) as missing_exc:
        verify_api_key(api_key=None, settings=settings)
    with pytest.raises(HTTPException) as invalid_exc:
        verify_api_key(api_key="not-the-right-token", settings=settings)

    assert missing_exc.value.detail == invalid_exc.value.detail


def test_valid_token_does_not_raise(settings: Settings) -> None:
    verify_api_key(api_key="valid-token", settings=settings)


def test_any_of_multiple_configured_tokens_is_accepted(
    multi_token_settings: Settings,
) -> None:
    verify_api_key(api_key="app1-token", settings=multi_token_settings)
    verify_api_key(api_key="app2-token", settings=multi_token_settings)
    verify_api_key(api_key="app3-token", settings=multi_token_settings)


def test_comparison_uses_compare_digest(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    original = security.secrets.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(security.secrets, "compare_digest", spy)

    verify_api_key(api_key="valid-token", settings=settings)

    assert calls
    assert all(call == ("valid-token", "valid-token") for call in calls)
