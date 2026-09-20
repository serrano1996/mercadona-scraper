from pydantic import computed_field
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def api_keys(self) -> frozenset[str]:
        return frozenset(key.strip() for key in self.API_KEYS.split(",") if key.strip())
