from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MERCADONA_BASE_URL: str
    REDIS_URL: str
    CACHE_TTL_SECONDS: int = 3600
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_BASE_DELAY: float = 0.5
