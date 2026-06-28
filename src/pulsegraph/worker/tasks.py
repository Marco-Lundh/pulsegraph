"""Worker task: run one watch's pipeline and persist the outcome (ADR 0015)."""

import asyncio
import datetime
import uuid
from dataclasses import replace

import redis as redis_lib
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import PipelineRun, Watch
from pulsegraph.domain.enums import ModelKind, RunStatus
from pulsegraph.observability import traced_run
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.contracts import WatchSpec
from pulsegraph.pipeline.graph import run_pipeline
from pulsegraph.redis_client import check_rate
from pulsegraph.worker.persistence import (
    load_dedup_memory,
    persist_run_results,
)
from pulsegraph.worker.sinks import build_notification_sink

# ---------------------------------------------------------------------------
# Core pipeline runner (testable without arq)
# ---------------------------------------------------------------------------


def run_watch_core(
    db: Session,
    watch: Watch,
    deps: PipelineDeps,
    redis_client: redis_lib.Redis | None = None,
) -> dict:
    """Execute the pipeline for *watch*, persist the run record.

    Idempotency: bails out if a RUNNING run already exists for this watch.
    Rate limiting: skips if the user exceeded their hourly quota. When
    *redis_client* is None (offline / tests) the rate limit is not enforced.
    """
    existing = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.watch_id == watch.id,
            PipelineRun.status == RunStatus.RUNNING,
        )
        .first()
    )
    if existing is not None:
        return {"skipped": "already_running", "run_id": str(existing.id)}

    if redis_client is not None:
        limit = get_settings().max_runs_per_hour_per_user
        if not check_rate(redis_client, watch.user_id, limit):
            return {"skipped": "rate_limit", "user_id": str(watch.user_id)}

    run = PipelineRun(
        watch_id=watch.id,
        status=RunStatus.RUNNING,
        started_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(run)
    db.flush()
    # Commit the RUNNING record on its own so that rolling back a failed
    # run's partial provenance still leaves the run row to mark FAILED.
    db.commit()

    spec = WatchSpec(
        user_id=str(watch.user_id),
        source=watch.source,
        query=watch.prompt,
    )

    settings = get_settings()
    # Seed cross-run memory from the DB so the Fetcher skips already-stored
    # items and the Notifier never re-delivers (ADR 0003/0016).
    seen_hashes, sent_dedup_keys = load_dedup_memory(
        db, watch.user_id, lookback_days=settings.dedup_lookback_days
    )
    # Bind the notification channels to this run's session (ADR 0016).
    run_deps = replace(deps, sink=build_notification_sink(settings, db))

    try:
        # Trace the LangGraph execution to LangSmith when enabled; the
        # captured trace id is persisted below so the run links to it
        # (ADR 0007). A no-op when tracing is off (local-first).
        with traced_run(settings) as trace:
            state = run_pipeline(
                run_deps,
                spec,
                seen_hashes=seen_hashes,
                sent_dedup_keys=sent_dedup_keys,
            )
        item_count = len(state.get("items") or [])
        persist_run_results(
            db,
            run,
            watch,
            state,
            embedding_model=run_deps.embedder.model_name,
            model_versions={
                ModelKind.CLAUDE: settings.anthropic_model,
                ModelKind.OLLAMA: settings.ollama_model,
            },
        )
        run.status = RunStatus.SUCCEEDED
    except Exception as exc:
        # Discard any half-written provenance; keep a FAILED run record.
        db.rollback()
        run.status = RunStatus.FAILED
        run.error = str(exc)
        item_count = 0
        raise
    finally:
        now = datetime.datetime.now(datetime.UTC)
        run.finished_at = now
        run.langsmith_trace_id = trace.trace_id
        watch.last_run_at = now
        watch.next_run_at = now + watch.schedule_interval
        db.commit()

    return {"run_id": str(run.id), "items": item_count}


# ---------------------------------------------------------------------------
# arq task entry point
# ---------------------------------------------------------------------------


async def run_watch(ctx: dict, watch_id: str) -> dict:
    """arq task: run the pipeline for one watch (ADR 0015)."""
    db: Session = ctx["db_factory"]()
    try:
        watch = db.get(Watch, uuid.UUID(watch_id))
        if watch is None or not watch.is_active:
            return {"skipped": "not_found_or_inactive"}
        deps: PipelineDeps = ctx["pipeline_deps"]
        redis_client: redis_lib.Redis | None = ctx.get("redis")
        return await asyncio.to_thread(
            run_watch_core, db, watch, deps, redis_client
        )
    finally:
        db.close()
