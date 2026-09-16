"""T18 — sanity check that the shared integration fixtures (real app +
real lifespan, fakeredis swapped in for Redis) work end to end."""

import fakeredis
from httpx import AsyncClient

from app.main import app as fastapi_app


async def test_docs_loads(client: AsyncClient) -> None:
    response = await client.get("/docs")

    assert response.status_code == 200


async def test_redis_is_really_swapped_for_fakeredis(client: AsyncClient) -> None:
    cache_repository = fastapi_app.state.cache_repository

    assert isinstance(cache_repository._redis, fakeredis.FakeAsyncRedis)
