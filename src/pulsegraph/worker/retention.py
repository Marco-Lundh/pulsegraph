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
of a user reaches checkpoints too (see :mod:`pulsegraph.api.erasure`), so
they are not left until the next retention pass.
"""

import datetime
import logging

from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import Item, PipelineRun
from pulsegraph.pipeline.checkpointer import delete_threads

logger = logging.getLogger(__name__)


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

    checkpoints = delete_threads(checkpointer, [str(run.id) for run in runs])

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
