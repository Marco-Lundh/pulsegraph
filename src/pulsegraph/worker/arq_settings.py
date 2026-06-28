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
from pulsegraph.pipeline.hybrid import HybridModelClient
from pulsegraph.pipeline.local import DictSourceRegistry, InMemorySink
from pulsegraph.pipeline.ollama import OllamaEmbedder, OllamaModelClient
from pulsegraph.redis_client import make_redis
from pulsegraph.sources.entsoe import EntsoePlugin
from pulsegraph.sources.jobtech import JobTechPlugin
from pulsegraph.sources.riksdagen import RiksdagenPlugin
from pulsegraph.worker.alerts import run_alerts
from pulsegraph.worker.digest import run_digest
from pulsegraph.worker.retention import run_retention
from pulsegraph.worker.scheduler import enqueue_due_watches
from pulsegraph.worker.tasks import run_watch


def _build_pipeline_deps(settings) -> PipelineDeps:
    """Wire the pipeline to real local/cloud adapters (ADR 0002).

    The notification sink is a placeholder here; ``worker.tasks`` swaps in
    a per-run sink bound to the run's DB session (ADR 0016).
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
    )


async def startup(ctx: dict) -> None:
    settings = get_settings()
    # Turn on LangSmith tracing for the worker process when configured
    # (ADR 0007); a no-op under the local-first default.
    configure_tracing(settings)
    engine = create_engine(settings.database_url)
    ctx["db_factory"] = sessionmaker(bind=engine)
    r = make_redis(settings.redis_url)
    ctx["redis"] = r
    ctx["pipeline_deps"] = _build_pipeline_deps(settings)


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [run_watch]
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
    ]
    on_startup = startup
    on_shutdown = shutdown

    @classmethod
    def redis_settings(cls) -> RedisSettings:
        return RedisSettings.from_dsn(get_settings().redis_url)
