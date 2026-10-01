from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MERCADONA_BASE_URL: str
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 3600
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_BASE_DELAY: float = 0.5
    RETRY_JITTER_MAX_S: float = 0.3
    LOG_LEVEL: str = "INFO"
    # Comma-separated valid API tokens for GET /api/v1/* (spec 004 RF-5).
    # Empty by default: no token configured means no token is valid.
    API_KEYS: str = ""
    # Cache TTLs for postal_code -> warehouse resolution (spec 007 RF-3,
    # RF-11). Longer than CACHE_TTL_SECONDS: warehouse assignment changes
    # far less often than product catalog/prices. The negative TTL (postal
    # codes with no Mercadona service) is shorter so a new service area is
    # picked up sooner.
    WAREHOUSE_CACHE_TTL_SECONDS: int = 86400
    WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS: int = 3600
    # Timeouts (spec 010 RF-1/RF-4). Redis had none: a Redis that accepted
    # the connection but never answered hung the request forever instead
    # of degrading to "no cache". One value for connect and per-operation
    # timeouts. HTTP keeps httpx's implicit 5s default, now explicit.
    REDIS_TIMEOUT_SECONDS: float = Field(default=1.0, gt=0)
    HTTP_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_keys(self) -> frozenset[str]:
        return frozenset(key.strip() for key in self.API_KEYS.split(",") if key.strip())
