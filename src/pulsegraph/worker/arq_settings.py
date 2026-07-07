"""arq WorkerSettings — wires up Redis, DB session factory, pipeline deps."""

import anthropic
from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pulsegraph.config import get_settings
from pulsegraph.observability import configure_tracing
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.anthropic_client import ClaudeModelClient
from pulsegraph.pipeline.checkpointer import build_checkpointer
from pulsegraph.pipeline.hybrid import HybridModelClient
from pulsegraph.pipeline.local import DictSourceRegistry, InMemorySink
from pulsegraph.pipeline.ollama import OllamaEmbedder, OllamaModelClient
from pulsegraph.pipeline.prompts import ensure_default_prompts
from pulsegraph.redis_client import make_redis
from pulsegraph.sources.entsoe import EntsoePlugin
from pulsegraph.sources.jobtech import JobTechPlugin
from pulsegraph.sources.riksdagen import RiksdagenPlugin
from pulsegraph.worker.alerts import run_alerts
from pulsegraph.worker.digest import run_digest
from pulsegraph.worker.drift import run_drift_recheck
from pulsegraph.worker.reembed import run_reembed
from pulsegraph.worker.retention import run_retention
from pulsegraph.worker.retry import run_instant_retry
from pulsegraph.worker.scheduler import enqueue_due_watches
from pulsegraph.worker.tasks import run_watch


def _build_pipeline_deps(settings, checkpointer=None) -> PipelineDeps:
    """Wire the pipeline to real local/cloud adapters (ADR 0002).

    The notification sink is a placeholder here; ``worker.tasks`` swaps in
    a per-run sink bound to the run's DB session (ADR 0016). ``checkpointer``
    persists each run's graph state when configured (ADR 0001).
    """
    registry = DictSourceRegistry()
    registry.register(JobTechPlugin())
    registry.register(RiksdagenPlugin())
    registry.register(EntsoePlugin(settings.entsoe_api_token))

    r = make_redis(settings.redis_url)

    local = OllamaModelClient(
        settings.ollama_base_url,
        settings.ollama_model,
        timeout=settings.ollama_timeout_seconds,
    )
    cloud = None
    if settings.cloud_model_available:
        cloud = ClaudeModelClient(
            anthropic.Anthropic(api_key=settings.anthropic_api_key),
            settings.anthropic_model,
            redis_client=r,
            cost_cap_usd=settings.monthly_cost_cap_usd,
            input_cost_per_token=settings.anthropic_input_cost_per_token,
            output_cost_per_token=settings.anthropic_output_cost_per_token,
        )

    embedder = OllamaEmbedder(
        settings.ollama_base_url,
        settings.ollama_embedding_model,
        timeout=settings.ollama_timeout_seconds,
    )
    return PipelineDeps(
        registry=registry,
        embedder=embedder,
        model=HybridModelClient(local, cloud),
        sink=InMemorySink(),
        cloud_available=settings.cloud_model_available,
        redis_client=r,
        fetch_cache_ttl=settings.fetch_cache_ttl_seconds,
        checkpointer=checkpointer,
    )


async def startup(ctx: dict) -> None:
    settings = get_settings()
    # Refuse to start a non-local worker configured with the dev JWT secret
    # (ADR 0009/0021); a no-op locally.
    settings.validate_production_secrets()
    # Turn on LangSmith tracing for the worker process when configured
    # (ADR 0007); a no-op under the local-first default.
    configure_tracing(settings)
    engine = create_engine(settings.database_url)
    ctx["db_factory"] = sessionmaker(bind=engine)
    # Ensure the analyzer/evaluator prompts exist so every Analysis can pin
    # its versioned prompt (ADR 0011); idempotent, safe on every startup.
    with ctx["db_factory"]() as session:
        ensure_default_prompts(session)
    r = make_redis(settings.redis_url)
    ctx["redis"] = r
    # Build the graph state checkpointer once (ADR 0001); persist a handle to
    # release its resources (the Postgres pool) at shutdown.
    checkpointer, close_checkpointer = build_checkpointer(settings)
    ctx["checkpointer_close"] = close_checkpointer
    ctx["pipeline_deps"] = _build_pipeline_deps(settings, checkpointer)


async def shutdown(ctx: dict) -> None:
    close = ctx.get("checkpointer_close")
    if close is not None:
        close()


class WorkerSettings:
    functions = [run_watch]
    # Retry a failed job with arq's built-in backoff, up to this many
    # attempts, before ``run_watch`` deactivates the watch (ADR 0015).
    max_tries = get_settings().worker_max_tries
    # arq reads this on the class, so it must be a RedisSettings instance,
    # not a method — evaluated once at import like max_tries above
    # (get_settings() is cached, so it is the process-wide config).
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    cron_jobs = [
        cron(
            enqueue_due_watches,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
        # GDPR retention purge, once daily at 03:00 (ADR 0018).
        cron(run_retention, hour=3, minute=0),
        # Daily notification digest, once daily at 06:00 (ADR 0016).
        cron(run_digest, hour=6, minute=0),
        # Operator alert sweep, every 15 minutes (ADR 0020).
        cron(run_alerts, minute={0, 15, 30, 45}),
        # Auto-resume drift-paused sources that recovered, hourly (ADR 0010).
        cron(run_drift_recheck, minute=30),
        # Re-embed items stale for the current embedding model, daily at
        # 04:00 (ADR 0014).
        cron(run_reembed, hour=4, minute=0),
        # Retry failed instant email/webhook deliveries, every 10 minutes
        # (ADR 0016).
        cron(run_instant_retry, minute={0, 10, 20, 30, 40, 50}),
    ]
    on_startup = startup
    on_shutdown = shutdown
