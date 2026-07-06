"""Application settings, loaded from the environment (ADR 0009).

The defaults are deliberately local-first (ADR 0017): with no `.env`
present the system targets a local database, a local Redis, and the
local Ollama model, and never calls a cloud service.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The built-in JWT secret. Fine locally; rejected in any non-local env by
# ``Settings.validate_production_secrets`` (ADR 0009/0021).
_DEFAULT_JWT_SECRET = "dev-secret-change-in-prod"
# HMAC-SHA256's recommended minimum key length (RFC 7518 §3.2).
_MIN_JWT_SECRET_BYTES = 32


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
        default=_DEFAULT_JWT_SECRET, alias="JWT_SECRET_KEY"
    )
    jwt_expire_hours: int = Field(default=24, alias="JWT_EXPIRE_HOURS")

    # Graph state checkpointing (ADR 0001). "none" (local-first default,
    # no overhead) compiles the graph without a checkpointer; "memory" keeps
    # per-process checkpoints (dev/debug); "postgres" persists every run's
    # graph state durably so it survives a restart and can be inspected /
    # replayed (time-travel, rollback). The Postgres saver manages its own
    # checkpoint tables via its setup() — not Alembic.
    checkpointer_backend: Literal["none", "memory", "postgres"] = Field(
        default="none", alias="CHECKPOINTER_BACKEND"
    )
    checkpointer_pool_size: int = Field(
        default=4, alias="CHECKPOINTER_POOL_SIZE"
    )

    langsmith_enabled: bool = Field(default=False, alias="LANGSMITH_ENABLED")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="pulsegraph", alias="LANGSMITH_PROJECT"
    )

    # Notification delivery channels (ADR 0016). Both are off by default
    # so the local-first system never reaches outside the machine.
    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    email_from: str = Field(
        default="alerts@pulsegraph.local", alias="EMAIL_FROM"
    )
    smtp_host: str = Field(default="localhost", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    webhook_enabled: bool = Field(default=False, alias="WEBHOOK_ENABLED")
    webhook_signing_secret: str = Field(
        default="", alias="WEBHOOK_SIGNING_SECRET"
    )

    use_recorded_fixtures: bool = Field(
        default=False, alias="USE_RECORDED_FIXTURES"
    )

    # Brute-force protection for the auth endpoints (ADR 0021). Each of
    # login and register allows this many attempts per window, per client
    # IP, before returning 429; the two actions have independent budgets.
    auth_rate_limit: int = Field(default=10, alias="AUTH_RATE_LIMIT")
    auth_rate_window_seconds: int = Field(
        default=300, alias="AUTH_RATE_WINDOW_SECONDS"
    )

    max_active_watches_per_user: int = Field(
        default=20, alias="MAX_ACTIVE_WATCHES_PER_USER"
    )
    max_runs_per_hour_per_user: int = Field(
        default=60, alias="MAX_RUNS_PER_HOUR_PER_USER"
    )
    # Worker retry policy (ADR 0015): how many times arq attempts a watch's
    # job before giving up. On the final failed attempt the watch is
    # deactivated so a permanently broken watch stops being scheduled.
    worker_max_tries: int = Field(default=3, alias="WORKER_MAX_TRIES")
    # Embedding versioning (ADR 0014): how many items the re-embed cron
    # re-embeds per run when the embedding model has changed, and how close
    # (cosine similarity, 0-1) two same-model vectors must be for the newer
    # item to count as a semantic duplicate and be suppressed.
    reembed_batch_size: int = Field(default=200, alias="REEMBED_BATCH_SIZE")
    embedding_similarity_threshold: float = Field(
        default=0.95, alias="EMBEDDING_SIMILARITY_THRESHOLD"
    )
    monthly_cost_cap_usd: float = Field(
        default=10.0, alias="MONTHLY_COST_CAP_USD"
    )
    # Operator alert threshold (ADR 0020): flag spend as near-cap once it
    # reaches this fraction of the monthly cap.
    cost_alert_threshold_ratio: float = Field(
        default=0.8, alias="COST_ALERT_THRESHOLD_RATIO"
    )
    # Operator alerts (ADR 0020): flag the queue as backlogged once this
    # many jobs are waiting, and runs as slow once p95 exceeds this many
    # seconds. Firing alerts are pushed to the operator webhook when set
    # (off by default → poll /admin/ops instead).
    queue_backlog_alert_threshold: int = Field(
        default=100, alias="QUEUE_BACKLOG_ALERT_THRESHOLD"
    )
    job_latency_alert_seconds: float = Field(
        default=300.0, alias="JOB_LATENCY_ALERT_SECONDS"
    )
    operator_webhook_url: str = Field(default="", alias="OPERATOR_WEBHOOK_URL")
    operator_webhook_secret: str = Field(
        default="", alias="OPERATOR_WEBHOOK_SECRET"
    )
    # Alert throttle/dedup (ADR 0020): once a given alert kind (worker
    # down, queue backlog, ...) has been pushed to the operator webhook,
    # suppress repeats of that same kind for this many seconds instead of
    # re-sending on every 15-minute sweep the condition stays firing.
    alert_throttle_seconds: int = Field(
        default=3600, alias="ALERT_THROTTLE_SECONDS"
    )
    fetch_cache_ttl_seconds: int = Field(
        default=900, alias="FETCH_CACHE_TTL_SECONDS"
    )
    # How far back to load a user's seen hashes / sent keys when seeding a
    # run's dedup memory (ADR 0003/0016). Bounds the per-run lookup; items
    # older than this may be re-analyzed, but the DB unique constraints
    # still prevent duplicate rows.
    dedup_lookback_days: int = Field(default=90, alias="DEDUP_LOOKBACK_DAYS")
    # Offline eval release gate (ADR 0012/0019): the minimum notify-F1 a
    # release must score on the golden datasets before it can ship.
    eval_min_f1: float = Field(default=0.7, alias="EVAL_MIN_F1")
    # GDPR data retention (ADR 0018): fetched items and their provenance
    # chain, plus pipeline-run traces, are purged once older than this
    # window. A scheduled job enforces it (see worker.retention).
    data_retention_days: int = Field(default=90, alias="DATA_RETENTION_DAYS")
    # Digest delivery retry cap (ADR 0016): a daily-digest notification is
    # retried once per day on push failure; after this many total failed
    # attempts it is dead-lettered (marked FAILED) instead of retrying
    # forever against a permanently broken destination.
    digest_max_attempts: int = Field(default=5, alias="DIGEST_MAX_ATTEMPTS")

    @property
    def cloud_model_available(self) -> bool:
        """Whether cloud routing is both enabled and configured.

        Guards against an enabled-but-unkeyed misconfiguration so the
        Analyzer can fall back to the local model instead of failing.
        """
        return self.use_cloud_model and bool(self.anthropic_api_key)

    def validate_production_secrets(self) -> None:
        """Fail fast if a non-local deployment still uses dev secrets.

        In any environment other than ``local`` the JWT signing key must be
        overridden from its built-in dev default and be at least 32 bytes
        (the HMAC-SHA256 minimum, RFC 7518 §3.2). A no-op locally so the
        local-first defaults keep working with no configuration (ADR
        0009/0021). Called at API and worker startup so a misconfigured
        production process refuses to start rather than signing tokens with
        a publicly known key.
        """
        if self.env == "local":
            return
        problems: list[str] = []
        if self.jwt_secret_key == _DEFAULT_JWT_SECRET:
            problems.append("JWT_SECRET_KEY is still the built-in dev default")
        elif len(self.jwt_secret_key.encode()) < _MIN_JWT_SECRET_BYTES:
            problems.append(
                "JWT_SECRET_KEY must be at least "
                f"{_MIN_JWT_SECRET_BYTES} bytes"
            )
        if problems:
            raise RuntimeError(
                f"Insecure configuration for PULSEGRAPH_ENV={self.env!r}: "
                + "; ".join(problems)
            )

    @property
    def langsmith_active(self) -> bool:
        """Whether LangSmith tracing is both enabled and configured.

        Off (the local-first default) unless tracing is enabled and an
        API key is present, so an enabled-but-unkeyed misconfiguration
        never attempts to reach the LangSmith service (ADR 0007).
        """
        return self.langsmith_enabled and bool(self.langsmith_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance for the process."""
    return Settings()
