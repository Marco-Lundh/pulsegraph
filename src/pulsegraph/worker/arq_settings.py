"""arq WorkerSettings — wires up Redis, DB session factory, pipeline deps."""

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pulsegraph.config import get_settings
from pulsegraph.domain.enums import SourceKind
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)
from pulsegraph.redis_client import make_redis
from pulsegraph.worker.scheduler import enqueue_due_watches
from pulsegraph.worker.tasks import run_watch


def _build_pipeline_deps(settings) -> PipelineDeps:
    """Wire pipeline adapters; replace stubs with real clients later."""
    registry = DictSourceRegistry()
    # Real source plugins will be registered here; stubs used for now.
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, []))
    registry.register(StaticSourcePlugin(SourceKind.RIKSDAGEN, []))
    registry.register(StaticSourcePlugin(SourceKind.ENTSOE, []))
    r = make_redis(settings.redis_url)
    return PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=InMemorySink(),
        cloud_available=settings.cloud_model_available,
        redis_client=r,
        fetch_cache_ttl=settings.fetch_cache_ttl_seconds,
    )


async def startup(ctx: dict) -> None:
    settings = get_settings()
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
    ]
    on_startup = startup
    on_shutdown = shutdown

    @classmethod
    def redis_settings(cls) -> RedisSettings:
        return RedisSettings.from_dsn(get_settings().redis_url)
