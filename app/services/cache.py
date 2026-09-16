from redis.asyncio import Redis

from app.models.product import ProductSearchResponse


class CacheRepository:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> ProductSearchResponse | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return ProductSearchResponse.model_validate_json(raw)

    async def set(self, key: str, value: ProductSearchResponse, ttl: int) -> None:
        await self._redis.set(key, value.model_dump_json(), ex=ttl)
