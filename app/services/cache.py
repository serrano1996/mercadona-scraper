import logging
from dataclasses import dataclass

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


@dataclass(frozen=True)
class CachedWarehouse:
    """A cached postal_code -> warehouse resolution. `warehouse` is None
    when the postal_code is cached as "not served" by Mercadona (spec 007
    RF-11), distinguishing that from a cache miss (no entry at all)."""

    warehouse: str | None


_WAREHOUSE_KEY_PREFIX = "postal-code-wh:"
_WAREHOUSE_UNSERVED_KEY_PREFIX = "postal-code-wh-unserved:"


class WarehouseCacheRepository:
    """Caches postal_code -> warehouse resolutions (spec 007 RF-3, RF-4,
    RF-11, Decision D3 in plan.md). Positive and negative ("not served")
    entries live under separate keys with independent TTLs; if both
    somehow coexist, the positive one wins, since a warehouse having
    started to serve a postal_code is a more useful signal than a stale
    negative entry."""

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def get(self, postal_code: str) -> CachedWarehouse | None:
        try:
            served, unserved = await self._redis.mget(
                _WAREHOUSE_KEY_PREFIX + postal_code, _WAREHOUSE_UNSERVED_KEY_PREFIX + postal_code
            )
        except RedisError:
            logger.warning(
                "Redis unavailable, skipping warehouse cache read for postal_code=%s",
                postal_code,
            )
            return None
        if served is not None:
            warehouse = served.decode() if isinstance(served, bytes) else served
            return CachedWarehouse(warehouse)
        if unserved is not None:
            return CachedWarehouse(None)
        return None

    async def set_served(self, postal_code: str, warehouse: str, ttl: int) -> None:
        try:
            await self._redis.set(_WAREHOUSE_KEY_PREFIX + postal_code, warehouse, ex=ttl)
        except RedisError:
            logger.warning(
                "Redis unavailable, skipping warehouse cache write for postal_code=%s",
                postal_code,
            )

    async def set_not_served(self, postal_code: str, ttl: int) -> None:
        try:
            await self._redis.set(_WAREHOUSE_UNSERVED_KEY_PREFIX + postal_code, "1", ex=ttl)
        except RedisError:
            logger.warning(
                "Redis unavailable, skipping warehouse cache write for postal_code=%s",
                postal_code,
            )
