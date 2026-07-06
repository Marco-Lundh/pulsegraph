"""Scheduled GDPR data retention: purge expired data (ADR 0018).

Enforces the per-table retention window from ADR 0018 on the same
scheduler as the pipeline (ADR 0015). Deleting an ``Item`` cascades to
its analysis/evaluation/notification provenance chain via the database's
ON DELETE CASCADE; deleting a ``PipelineRun`` removes the run trace while
leaving items and the cost ledger intact (their FK is ON DELETE SET
NULL). Audit-log entries are deliberately left untouched — they carry
their own, longer compliance retention.

The external LangSmith trace a run references (``langsmith_trace_id``) is
NOT purged here: the LangSmith SDK exposes no per-run delete API (only
whole-project deletion), so trace lifetime is governed by LangSmith's own
retention configuration. Tracing is off by default (local-first, ADR
0007), so no personal data leaves the machine unless it is explicitly
enabled — see docs/adr/TODO.md.

When the Postgres graph checkpointer is enabled (ADR 0001), each expired
run's checkpoints are purged too. Those tables (``checkpoints`` etc.) are
LangGraph's own, keyed by the run id and not FK-linked to ``pipeline_runs``,
so retention must reach them explicitly or a user's watch queries and
fetched content would outlive the retention window. Immediate GDPR erasure
of a user does not yet reach checkpoints — they are cleared on the next
retention pass; see docs/adr/TODO.md.
"""

import datetime
import logging

from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import Item, PipelineRun

logger = logging.getLogger(__name__)


def _purge_checkpoints(checkpointer: object, runs: list[PipelineRun]) -> int:
    """Delete the graph checkpoints for each expired run (ADR 0001).

    Best-effort and a no-op unless a checkpointer with a synchronous
    ``delete_thread`` is configured (the Postgres backend). Keyed by the run
    id, matching the ``thread_id`` used when the run was executed.
    """
    delete_thread = getattr(checkpointer, "delete_thread", None)
    if not callable(delete_thread):
        return 0
    purged = 0
    for run in runs:
        try:
            delete_thread(str(run.id))
            purged += 1
        except Exception:  # noqa: BLE001
            logger.exception("failed to purge checkpoints for run %s", run.id)
    return purged


def purge_expired_data(
    db: Session,
    *,
    now: datetime.datetime,
    retention_days: int,
    checkpointer: object = None,
) -> dict[str, int]:
    """Delete data older than the window; return per-table delete counts.

    The cutoff is applied both in the query (narrows the candidate set in
    production) and again in Python, so the window stays correct under
    test doubles that ignore filter expressions (mirrors
    :func:`worker.scheduler.select_due_watches`). When *checkpointer* is the
    durable graph checkpointer (ADR 0001), each expired run's checkpoints
    are purged with it.
    """
    cutoff = now - datetime.timedelta(days=retention_days)

    items = [
        row
        for row in db.query(Item).filter(Item.fetched_at < cutoff).all()
        if row.fetched_at < cutoff
    ]
    runs = [
        row
        for row in db.query(PipelineRun)
        .filter(PipelineRun.started_at < cutoff)
        .all()
        if row.started_at < cutoff
    ]

    checkpoints = _purge_checkpoints(checkpointer, runs)

    for row in (*items, *runs):
        db.delete(row)
    db.commit()

    return {
        "items": len(items),
        "runs": len(runs),
        "checkpoints": checkpoints,
    }


async def run_retention(ctx: dict) -> dict:
    """arq cron entry point: purge expired data on a fixed schedule."""
    settings = get_settings()
    db = ctx["db_factory"]()
    try:
        deps = ctx.get("pipeline_deps")
        return purge_expired_data(
            db,
            now=datetime.datetime.now(datetime.UTC),
            retention_days=settings.data_retention_days,
            checkpointer=getattr(deps, "checkpointer", None),
        )
    finally:
        db.close()
