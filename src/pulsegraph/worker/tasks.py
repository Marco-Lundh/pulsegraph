"""Worker task: run one watch's pipeline and persist the outcome (ADR 0015)."""

import asyncio
import datetime
import uuid
from dataclasses import replace

import redis as redis_lib
from arq import Retry
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import PipelineRun, Watch
from pulsegraph.domain.enums import ModelKind, PromptRole, RunStatus
from pulsegraph.observability import traced_run
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.contracts import WatchSpec
from pulsegraph.pipeline.graph import run_pipeline
from pulsegraph.pipeline.prompts import active_prompt_template
from pulsegraph.redis_client import check_rate
from pulsegraph.worker.digest import user_wants_digest
from pulsegraph.worker.persistence import (
    load_dedup_memory,
    mark_source_paused,
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
    # Bind the notification channels to this run's session (ADR 0016) and
    # load the active analyzer instruction from the registry so an admin's
    # edit takes effect at runtime (ADR 0011); None falls back to the
    # client's built-in default.
    run_deps = replace(
        deps,
        sink=build_notification_sink(settings, db),
        analyzer_instruction=active_prompt_template(db, PromptRole.ANALYZER),
    )

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
        drift_detail = state.get("drift_detail")
        if drift_detail:
            # The source's schema drifted: fail loud (ADR 0010). Pause the
            # source so the scheduler stops triggering it, and mark this run
            # PAUSED rather than SUCCEEDED. Nothing is persisted downstream.
            mark_source_paused(db, watch.source, drift_detail)
            run.status = RunStatus.PAUSED
            item_count = 0
        else:
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
                digest=user_wants_digest(db, watch.user_id),
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


def _deactivate_watch(db: Session, watch: Watch) -> None:
    """Stop scheduling a watch that has failed every retry (ADR 0015).

    Clears the source-plugin/pipeline failure by deactivating the watch so
    the scheduler skips it; the FAILED run records stay visible and the
    user can re-activate it from the dashboard once the cause is fixed.
    """
    db.rollback()
    watch.is_active = False
    db.commit()


async def run_watch(ctx: dict, watch_id: str) -> dict:
    """arq task: run the pipeline for one watch (ADR 0015).

    On an unhandled failure the job is retried with backoff up to
    ``worker_max_tries`` (WorkerSettings.max_tries); once the final attempt
    also fails the watch is deactivated so a permanently broken watch stops
    being scheduled forever.
    """
    db: Session = ctx["db_factory"]()
    try:
        watch = db.get(Watch, uuid.UUID(watch_id))
        if watch is None or not watch.is_active:
            return {"skipped": "not_found_or_inactive"}
        deps: PipelineDeps = ctx["pipeline_deps"]
        redis_client: redis_lib.Redis | None = ctx.get("redis")
        try:
            return await asyncio.to_thread(
                run_watch_core, db, watch, deps, redis_client
            )
        except Exception:
            job_try = ctx.get("job_try", 1)
            if job_try >= get_settings().worker_max_tries:
                _deactivate_watch(db, watch)
                return {"failed": "deactivated", "watch_id": watch_id}
            # Not the final attempt: re-enqueue via arq's Retry so the job
            # runs again with backoff. A plain re-raise would NOT be retried
            # — arq only retries Retry/CancelledError/RetryJob, every other
            # exception finishes the job as failed (arq worker.py). Backoff
            # grows with the attempt, capped so it never defers absurdly long.
            raise Retry(defer=min(2**job_try, 300)) from None
    finally:
        db.close()
