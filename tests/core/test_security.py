"""T2 — 004-mercadona-scraper-authentication: verify_api_key rejects a
missing or empty X-API-Key header with 401 (spec.md RF-2).

Extended for T3: token comparison against settings.api_keys, constant-time
via secrets.compare_digest (spec.md RF-1/RF-3/RF-4).

Extended for T4: a rejection also logs a WARNING with the requested path,
never the token value (spec.md RF-6)."""

import logging

import pytest
from fastapi import Depends, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core import security
from app.core.config import Settings
from app.core.security import verify_api_key


def _make_request(path: str = "/protected") -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": []})


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
        verify_api_key(request=_make_request(), api_key=None, settings=settings)

    assert exc_info.value.status_code == 401


def test_empty_header_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(request=_make_request(), api_key="", settings=settings)

    assert exc_info.value.status_code == 401


def test_missing_and_empty_header_raise_same_detail(settings: Settings) -> None:
    with pytest.raises(HTTPException) as missing_exc:
        verify_api_key(request=_make_request(), api_key=None, settings=settings)
    with pytest.raises(HTTPException) as empty_exc:
        verify_api_key(request=_make_request(), api_key="", settings=settings)

    assert missing_exc.value.detail == empty_exc.value.detail


def test_invalid_token_raises_401(settings: Settings) -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_api_key(request=_make_request(), api_key="not-the-right-token", settings=settings)

    assert exc_info.value.status_code == 401


def test_invalid_token_raises_same_detail_as_missing_header(settings: Settings) -> None:
    with pytest.raises(HTTPException) as missing_exc:
        verify_api_key(request=_make_request(), api_key=None, settings=settings)
    with pytest.raises(HTTPException) as invalid_exc:
        verify_api_key(request=_make_request(), api_key="not-the-right-token", settings=settings)

    assert missing_exc.value.detail == invalid_exc.value.detail


def test_valid_token_does_not_raise(settings: Settings) -> None:
    verify_api_key(request=_make_request(), api_key="valid-token", settings=settings)


def test_any_of_multiple_configured_tokens_is_accepted(
    multi_token_settings: Settings,
) -> None:
    verify_api_key(request=_make_request(), api_key="app1-token", settings=multi_token_settings)
    verify_api_key(request=_make_request(), api_key="app2-token", settings=multi_token_settings)
    verify_api_key(request=_make_request(), api_key="app3-token", settings=multi_token_settings)


def test_comparison_uses_compare_digest(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    original = security.secrets.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return original(a, b)

    monkeypatch.setattr(security.secrets, "compare_digest", spy)

    verify_api_key(request=_make_request(), api_key="valid-token", settings=settings)

    assert calls
    assert all(call == ("valid-token", "valid-token") for call in calls)


@pytest.fixture
def protected_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings

    @app.get("/protected", dependencies=[Depends(verify_api_key)])
    async def protected() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _security_logs(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if r.name == "app.core.security"]


async def test_missing_header_logs_warning_with_path(
    protected_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        transport = ASGITransport(app=protected_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/protected")

    assert response.status_code == 401
    logs = _security_logs(caplog.records)
    assert len(logs) == 1
    assert "/protected" in logs[0].getMessage()


async def test_invalid_token_logs_warning_without_leaking_token(
    protected_app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    sent_token = "not-the-right-token"

    with caplog.at_level(logging.WARNING):
        transport = ASGITransport(app=protected_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/protected", headers={"X-API-Key": sent_token})

    assert response.status_code == 401
    logs = _security_logs(caplog.records)
    assert len(logs) == 1
    assert sent_token not in logs[0].getMessage()
    assert all(sent_token not in record.getMessage() for record in caplog.records)
