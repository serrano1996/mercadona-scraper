import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.models.product import ProductSearchResponse

logger = logging.getLogger(__name__)


class CacheRepository:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def get(self, key: str) -> ProductSearchResponse | None:
        try:
            raw = await self._redis.get(key)
        except RedisError:
            logger.warning("Redis unavailable, skipping cache read for key %s", key)
            return None
        if raw is None:
            return None
        return ProductSearchResponse.model_validate_json(raw)

    async def set(self, key: str, value: ProductSearchResponse, ttl: int) -> None:
        try:
            await self._redis.set(key, value.model_dump_json(), ex=ttl)
        except RedisError:
            logger.warning("Redis unavailable, skipping cache write for key %s", key)
