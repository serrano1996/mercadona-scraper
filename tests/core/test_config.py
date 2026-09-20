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
