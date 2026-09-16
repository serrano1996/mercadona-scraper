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


def test_settings_env_overrides_defaults(
    required_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "5")

    settings = Settings()

    assert settings.CACHE_TTL_SECONDS == 60
    assert settings.RETRY_MAX_ATTEMPTS == 5


def test_settings_missing_required_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCADONA_BASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
