"""T8 — CacheRepository degrades gracefully when Redis is unreachable
(spec.md caso limite "Cache inaccesible": log a warning, never raise)."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.models.product import ProductOut, ProductSearchResponse, SearchMeta
from app.services.cache import CacheRepository


@pytest.fixture
def broken_redis_client() -> AsyncMock:
    client = AsyncMock()
    client.get.side_effect = RedisConnectionError("connection refused")
    client.set.side_effect = RedisConnectionError("connection refused")
    return client


@pytest.fixture
def sample_response() -> ProductSearchResponse:
    return ProductSearchResponse(
        search=SearchMeta(
            postal_code="28001",
            term="leche",
            warehouse="mad1",
            strategy_used="api",
            scraped_at=datetime.now(UTC),
            total_results=1,
        ),
        products=[
            ProductOut(
                id="1",
                name="Leche entera",
                price=1.05,
                price_format="1.05 €/L",
                image_url="https://example.com/1.jpg",
                category="Lácteos",
            )
        ],
    )


async def test_get_returns_none_when_redis_down(
    broken_redis_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    repo = CacheRepository(broken_redis_client)

    with caplog.at_level(logging.WARNING):
        result = await repo.get("search:28001:leche")

    assert result is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_set_does_not_raise_when_redis_down(
    broken_redis_client: AsyncMock,
    sample_response: ProductSearchResponse,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = CacheRepository(broken_redis_client)

    with caplog.at_level(logging.WARNING):
        await repo.set("search:28001:leche", sample_response, ttl=3600)

    assert any(record.levelno == logging.WARNING for record in caplog.records)
