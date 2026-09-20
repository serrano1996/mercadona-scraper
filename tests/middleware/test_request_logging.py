"""T4 — RequestLoggingMiddleware generates a request-id per request, binds
it via the ContextVar (T2), and logs INFO start/end lines around the
request (spec 003 RF-6/RF-7)."""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.logging_config import configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestLoggingMiddleware)

    @test_app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return test_app


def _request_logs(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if r.name == "app.middleware.request_logging"]


async def test_logs_start_and_end_with_matching_request_id(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging("INFO")

    with caplog.at_level(logging.INFO):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ping")

    assert response.status_code == 200
    logs = _request_logs(caplog.records)
    assert len(logs) == 2
    assert logs[0].request_id == logs[1].request_id
    assert "GET" in logs[0].getMessage()
    assert "/ping" in logs[0].getMessage()
    assert "200" in logs[1].getMessage()


async def test_different_requests_get_different_request_ids(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    configure_logging("INFO")

    with caplog.at_level(logging.INFO):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/ping")
            await client.get("/ping")

    logs = _request_logs(caplog.records)
    assert len(logs) == 4
    assert len({r.request_id for r in logs}) == 2
