"""T5 — WarehouseCacheRepository: positive resolutions (postal_code ->
warehouse) and negative ones (postal_code not served, RF-9/RF-11) live
under distinct keys with independent TTLs, and Redis being down degrades
to a miss/no-op instead of raising (Decision D3/D6 in plan.md)."""

import logging
from unittest.mock import AsyncMock

import pytest
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.cache import CachedWarehouse, WarehouseCacheRepository


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis()


async def test_set_served_then_get_returns_cached_warehouse(redis_client: FakeAsyncRedis) -> None:
    repo = WarehouseCacheRepository(redis_client)

    await repo.set_served("28001", "mad3", ttl=86400)
    result = await repo.get("28001")

    assert result == CachedWarehouse("mad3")


async def test_set_served_uses_positive_key_with_ttl(redis_client: FakeAsyncRedis) -> None:
    repo = WarehouseCacheRepository(redis_client)

    await repo.set_served("28001", "mad3", ttl=86400)

    ttl = await redis_client.ttl("postal-code-wh:28001")
    assert 0 < ttl <= 86400


async def test_set_not_served_then_get_returns_none_warehouse(
    redis_client: FakeAsyncRedis,
) -> None:
    repo = WarehouseCacheRepository(redis_client)

    await repo.set_not_served("99999", ttl=3600)
    result = await repo.get("99999")

    assert result == CachedWarehouse(None)


async def test_set_not_served_uses_unserved_key_and_no_positive_key(
    redis_client: FakeAsyncRedis,
) -> None:
    repo = WarehouseCacheRepository(redis_client)

    await repo.set_not_served("99999", ttl=3600)

    ttl = await redis_client.ttl("postal-code-wh-unserved:99999")
    assert 0 < ttl <= 3600
    assert await redis_client.exists("postal-code-wh:99999") == 0


async def test_get_returns_none_on_miss(redis_client: FakeAsyncRedis) -> None:
    repo = WarehouseCacheRepository(redis_client)

    result = await repo.get("00000")

    assert result is None


async def test_positive_entry_wins_when_both_keys_coexist(redis_client: FakeAsyncRedis) -> None:
    repo = WarehouseCacheRepository(redis_client)

    await repo.set_not_served("28001", ttl=3600)
    await repo.set_served("28001", "mad3", ttl=86400)
    result = await repo.get("28001")

    assert result == CachedWarehouse("mad3")


@pytest.fixture
def broken_redis_client() -> AsyncMock:
    client = AsyncMock()
    client.mget.side_effect = RedisConnectionError("connection refused")
    client.set.side_effect = RedisConnectionError("connection refused")
    return client


async def test_get_returns_none_when_redis_down(
    broken_redis_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    repo = WarehouseCacheRepository(broken_redis_client)

    with caplog.at_level(logging.WARNING):
        result = await repo.get("28001")

    assert result is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_set_served_does_not_raise_when_redis_down(
    broken_redis_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    repo = WarehouseCacheRepository(broken_redis_client)

    with caplog.at_level(logging.WARNING):
        await repo.set_served("28001", "mad3", ttl=86400)

    assert any(record.levelno == logging.WARNING for record in caplog.records)


async def test_set_not_served_does_not_raise_when_redis_down(
    broken_redis_client: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    repo = WarehouseCacheRepository(broken_redis_client)

    with caplog.at_level(logging.WARNING):
        await repo.set_not_served("99999", ttl=3600)

    assert any(record.levelno == logging.WARNING for record in caplog.records)
