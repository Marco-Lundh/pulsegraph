"""Graph state checkpointing backends (ADR 0001).

LangGraph persists the graph state after each super-step to a checkpointer,
which is what makes state persistence, time-travel debugging and rollback
available at runtime (ADR 0001) instead of only in principle. The backend
is selected by config:

- ``none`` — the local-first default; the graph compiles without a
  checkpointer and runs exactly as before, no overhead.
- ``memory`` — an in-process saver, useful for local debugging (its
  checkpoints do not survive a restart and accumulate in memory).
- ``postgres`` — a durable saver: every run's state is persisted to
  Postgres keyed by its run id, so it survives a restart and can be
  inspected or replayed. The saver manages its own checkpoint tables via
  ``setup()`` (LangGraph's mechanism, not Alembic).
"""

import logging
from collections.abc import Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from pulsegraph.config import Settings

logger = logging.getLogger(__name__)

# The pipeline's own state types that get serialized into a checkpoint.
# Allow-listing them explicitly keeps checkpoint deserialization working
# (and typed, not degraded to plain dicts) across LangGraph versions that
# will otherwise block unregistered types — while still refusing arbitrary
# types, so a tampered checkpoint can't instantiate anything it likes.
_ALLOWED_MSGPACK_MODULES = [
    ("pulsegraph.domain.enums", "EvalStatus"),
    ("pulsegraph.domain.enums", "ModelKind"),
    ("pulsegraph.domain.enums", "SourceKind"),
    ("pulsegraph.pipeline.contracts", "WatchSpec"),
    ("pulsegraph.pipeline.contracts", "AnalysisResult"),
    ("pulsegraph.pipeline.contracts", "AnalysisRecord"),
    ("pulsegraph.pipeline.contracts", "EvaluationRecord"),
    ("pulsegraph.pipeline.contracts", "NotificationDraft"),
    ("pulsegraph.sources.base", "FetchedItem"),
]


def _serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES)


def _noop() -> None:
    pass


def build_checkpointer(
    settings: Settings,
) -> tuple[BaseCheckpointSaver | None, Callable[[], None]]:
    """Return ``(checkpointer, close)`` for the configured backend.

    ``close`` releases any resources (the Postgres connection pool) and is a
    no-op for the disabled and in-memory backends. If the Postgres backend
    cannot be initialized the worker degrades to no checkpointer rather than
    failing to start.
    """
    backend = settings.checkpointer_backend
    if backend == "none":
        return None, _noop
    if backend == "memory":
        return MemorySaver(serde=_serde()), _noop
    if backend == "postgres":
        return _postgres_checkpointer(settings)
    raise ValueError(f"unknown checkpointer_backend: {backend!r}")


def _postgres_checkpointer(
    settings: Settings,
) -> tuple[BaseCheckpointSaver | None, Callable[[], None]]:
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        # PostgresSaver speaks plain psycopg, so drop SQLAlchemy's dialect
        # suffix. A pool makes it safe to use from the worker's threads.
        uri = settings.database_url.replace(
            "postgresql+psycopg://", "postgresql://"
        )
        # min_size is set explicitly: the pool library defaults it to 4, so
        # a configured max_size below that would raise and silently disable
        # the checkpointer via the fallback below.
        pool = ConnectionPool(
            conninfo=uri,
            min_size=1,
            max_size=max(1, settings.checkpointer_pool_size),
            open=True,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        checkpointer = PostgresSaver(pool, serde=_serde())
        checkpointer.setup()
        return checkpointer, pool.close
    except Exception:  # noqa: BLE001
        logger.exception(
            "postgres checkpointer unavailable; running without one"
        )
        return None, _noop


def checkpoint_history(
    checkpointer: BaseCheckpointSaver | None, thread_id: str
) -> list:
    """Return a run's persisted checkpoints, newest first (ADR 0001).

    Each entry is the graph state saved at one super-step of the run
    identified by ``thread_id`` (the run id in production) — the raw
    material for time-travel inspection or replay. Empty when checkpointing
    is disabled.
    """
    if checkpointer is None:
        return []
    config = {"configurable": {"thread_id": thread_id}}
    return list(checkpointer.list(config))
