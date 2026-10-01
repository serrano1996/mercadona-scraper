"""T2 — Settings loads config from env vars with the defaults defined in plan.md."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCADONA_BASE_URL", "https://example.com/api")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


def test_settings_reads_required_env_vars(required_env: None) -> None:
    settings = Settings()

    assert settings.MERCADONA_BASE_URL == "https://example.com/api"
    assert settings.REDIS_URL == "redis://localhost:6379/0"


def test_settings_defaults(required_env: None) -> None:
    settings = Settings()

    assert settings.CACHE_TTL_SECONDS == 3600
    assert settings.RETRY_MAX_ATTEMPTS == 3
    assert settings.RETRY_BASE_DELAY > 0
    assert settings.RETRY_JITTER_MAX_S == 0.3
    assert settings.LOG_LEVEL == "INFO"


def test_settings_env_overrides_defaults(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("RETRY_JITTER_MAX_S", "0.75")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings()

    assert settings.CACHE_TTL_SECONDS == 60
    assert settings.RETRY_MAX_ATTEMPTS == 5
    assert settings.RETRY_JITTER_MAX_S == 0.75
    assert settings.LOG_LEVEL == "DEBUG"


def test_settings_missing_required_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCADONA_BASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_api_keys_defaults_to_empty(required_env: None) -> None:
    """T1 — 004-mercadona-scraper-authentication: no API_KEYS configured
    means no token is valid (spec.md RF-5)."""
    settings = Settings()

    assert settings.API_KEYS == ""
    assert settings.api_keys == frozenset()


def test_api_keys_parses_comma_separated_values(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "a,b,c")

    settings = Settings()

    assert settings.api_keys == {"a", "b", "c"}


def test_api_keys_strips_whitespace_around_commas(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", "a, b ,c")

    settings = Settings()

    assert settings.api_keys == {"a", "b", "c"}


def test_api_keys_ignores_empty_entries(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("API_KEYS", ",,")

    settings = Settings()

    assert settings.api_keys == frozenset()


def test_warehouse_ttl_defaults(required_env: None) -> None:
    """T1 — 007-mercadona-scraper-warehouse-resolution: default TTLs for
    the postal_code -> warehouse cache (spec.md RF-3, RF-11)."""
    settings = Settings()

    assert settings.WAREHOUSE_CACHE_TTL_SECONDS == 86400
    assert settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS == 3600


def test_warehouse_ttl_env_overrides_defaults(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAREHOUSE_CACHE_TTL_SECONDS", "120")
    monkeypatch.setenv("WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS", "30")

    settings = Settings()

    assert settings.WAREHOUSE_CACHE_TTL_SECONDS == 120
    assert settings.WAREHOUSE_NEGATIVE_CACHE_TTL_SECONDS == 30


def test_timeout_defaults(required_env: None) -> None:
    """T1 — 010-mercadona-scraper-operational-robustness, RF-1/RF-4: Redis
    gets a 1s timeout (it had none: a hung Redis hung the request), HTTP
    keeps httpx's implicit 5s, now explicit."""
    settings = Settings()

    assert settings.REDIS_TIMEOUT_SECONDS == 1.0
    assert settings.HTTP_TIMEOUT_SECONDS == 5.0


def test_timeouts_env_overrides_defaults(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_TIMEOUT_SECONDS", "0.3")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "2.5")

    settings = Settings()

    assert settings.REDIS_TIMEOUT_SECONDS == 0.3
    assert settings.HTTP_TIMEOUT_SECONDS == 2.5


@pytest.mark.parametrize("variable", ["REDIS_TIMEOUT_SECONDS", "HTTP_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_non_positive_timeouts_are_rejected(
    required_env: None, monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    """T1 — spec 010 casos límite: a zero or negative timeout fails fast at
    startup, like any other invalid setting."""
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError):
        Settings()
