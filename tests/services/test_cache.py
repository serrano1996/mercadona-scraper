"""T7 — CacheRepository: set followed by get returns the same deserialized object."""

from datetime import UTC, datetime

import pytest
from fakeredis import FakeAsyncRedis

from app.models.product import ProductOut, ProductSearchResponse, SearchMeta
from app.services.cache import CacheRepository


@pytest.fixture
def redis_client() -> FakeAsyncRedis:
    return FakeAsyncRedis()


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


async def test_set_then_get_returns_same_object(
    redis_client: FakeAsyncRedis, sample_response: ProductSearchResponse
) -> None:
    repo = CacheRepository(redis_client)

    await repo.set("search:28001:leche", sample_response, ttl=3600)
    result = await repo.get("search:28001:leche")

    assert result == sample_response


async def test_get_missing_key_returns_none(redis_client: FakeAsyncRedis) -> None:
    repo = CacheRepository(redis_client)

    result = await repo.get("does-not-exist")

    assert result is None
