"""Worker task: run one watch's pipeline and persist the outcome (ADR 0015)."""

import asyncio
import datetime
import uuid

import redis as redis_lib
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import PipelineRun, Watch
from pulsegraph.domain.enums import RunStatus
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.contracts import WatchSpec
from pulsegraph.pipeline.graph import run_pipeline
from pulsegraph.redis_client import check_rate

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

    spec = WatchSpec(
        user_id=str(watch.user_id),
        source=watch.source,
        query=watch.prompt,
    )

    try:
        state = run_pipeline(deps, spec)
        run.status = RunStatus.SUCCEEDED
        item_count = len(state.get("items") or [])
    except Exception as exc:
        run.status = RunStatus.FAILED
        run.error = str(exc)
        item_count = 0
        raise
    finally:
        now = datetime.datetime.now(datetime.UTC)
        run.finished_at = now
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
