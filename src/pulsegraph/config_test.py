"""Tests for application settings."""

from pulsegraph.config import Settings


def _settings(**env: str) -> Settings:
    """Build Settings from an explicit env mapping, ignoring .env."""
    return Settings(_env_file=None, **env)


# --- defaults ---


def test_defaults_are_local_first() -> None:
    settings = _settings()

    assert settings.env == "local"
    assert "localhost" in settings.database_url
    assert settings.use_cloud_model is False
    assert settings.langsmith_enabled is False
    assert settings.data_retention_days == 90


# --- cloud_model_available ---


def test_cloud_unavailable_when_disabled() -> None:
    settings = _settings(USE_CLOUD_MODEL="false", ANTHROPIC_API_KEY="k")

    assert settings.cloud_model_available is False


def test_cloud_unavailable_when_enabled_but_unkeyed() -> None:
    settings = _settings(USE_CLOUD_MODEL="true", ANTHROPIC_API_KEY="")

    assert settings.cloud_model_available is False


def test_cloud_available_when_enabled_and_keyed() -> None:
    settings = _settings(USE_CLOUD_MODEL="true", ANTHROPIC_API_KEY="k")

    assert settings.cloud_model_available is True


# --- langsmith_active ---


def test_langsmith_inactive_by_default() -> None:
    assert _settings().langsmith_active is False


def test_langsmith_inactive_when_enabled_but_unkeyed() -> None:
    settings = _settings(LANGSMITH_ENABLED="true", LANGSMITH_API_KEY="")

    assert settings.langsmith_active is False


def test_langsmith_active_when_enabled_and_keyed() -> None:
    settings = _settings(LANGSMITH_ENABLED="true", LANGSMITH_API_KEY="k")

    assert settings.langsmith_active is True
