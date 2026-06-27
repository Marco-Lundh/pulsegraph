"""Application settings, loaded from the environment (ADR 0009).

The defaults are deliberately local-first (ADR 0017): with no `.env`
present the system targets a local database, a local Redis, and the
local Ollama model, and never calls a cloud service.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="local", alias="PULSEGRAPH_ENV")

    database_url: str = Field(
        default=(
            "postgresql+psycopg://pulsegraph:pulsegraph"
            "@localhost:5432/pulsegraph"
        ),
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0", alias="REDIS_URL"
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.1:8b", alias="OLLAMA_MODEL")
    ollama_embedding_model: str = Field(
        default="nomic-embed-text", alias="OLLAMA_EMBEDDING_MODEL"
    )
    ollama_timeout_seconds: float = Field(
        default=60.0, alias="OLLAMA_TIMEOUT_SECONDS"
    )

    use_cloud_model: bool = Field(default=False, alias="USE_CLOUD_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-opus-4-8", alias="ANTHROPIC_MODEL"
    )

    # Claude pricing in USD per input/output token (claude-opus-4-8:
    # $5 / $25 per million). Used to meter spend against the cost cap.
    anthropic_input_cost_per_token: float = Field(
        default=5.0 / 1_000_000, alias="ANTHROPIC_INPUT_COST_PER_TOKEN"
    )
    anthropic_output_cost_per_token: float = Field(
        default=25.0 / 1_000_000, alias="ANTHROPIC_OUTPUT_COST_PER_TOKEN"
    )

    entsoe_api_token: str = Field(default="", alias="ENTSOE_API_TOKEN")
    entsoe_base_url: str = Field(
        default="https://web-api.tp.entsoe.eu/api", alias="ENTSOE_BASE_URL"
    )

    jwt_secret_key: str = Field(
        default="dev-secret-change-in-prod", alias="JWT_SECRET_KEY"
    )
    jwt_expire_hours: int = Field(default=24, alias="JWT_EXPIRE_HOURS")

    langsmith_enabled: bool = Field(default=False, alias="LANGSMITH_ENABLED")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")

    use_recorded_fixtures: bool = Field(
        default=False, alias="USE_RECORDED_FIXTURES"
    )

    max_active_watches_per_user: int = Field(
        default=20, alias="MAX_ACTIVE_WATCHES_PER_USER"
    )
    max_runs_per_hour_per_user: int = Field(
        default=60, alias="MAX_RUNS_PER_HOUR_PER_USER"
    )
    monthly_cost_cap_usd: float = Field(
        default=10.0, alias="MONTHLY_COST_CAP_USD"
    )
    fetch_cache_ttl_seconds: int = Field(
        default=900, alias="FETCH_CACHE_TTL_SECONDS"
    )

    @property
    def cloud_model_available(self) -> bool:
        """Whether cloud routing is both enabled and configured.

        Guards against an enabled-but-unkeyed misconfiguration so the
        Analyzer can fall back to the local model instead of failing.
        """
        return self.use_cloud_model and bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance for the process."""
    return Settings()
