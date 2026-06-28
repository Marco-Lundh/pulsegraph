"""Scheduled GDPR data retention: purge expired data (ADR 0018).

Enforces the per-table retention window from ADR 0018 on the same
scheduler as the pipeline (ADR 0015). Deleting an ``Item`` cascades to
its analysis/evaluation/notification provenance chain via the database's
ON DELETE CASCADE; deleting a ``PipelineRun`` removes the run trace while
leaving items and the cost ledger intact (their FK is ON DELETE SET
NULL). Audit-log entries are deliberately left untouched — they carry
their own, longer compliance retention.
"""

import datetime

from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
from pulsegraph.db.models import Item, PipelineRun


def purge_expired_data(
    db: Session,
    *,
    now: datetime.datetime,
    retention_days: int,
) -> dict[str, int]:
    """Delete data older than the window; return per-table delete counts.

    The cutoff is applied both in the query (narrows the candidate set in
    production) and again in Python, so the window stays correct under
    test doubles that ignore filter expressions (mirrors
    :func:`worker.scheduler.select_due_watches`).
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

    for row in (*items, *runs):
        db.delete(row)
    db.commit()

    return {"items": len(items), "runs": len(runs)}


async def run_retention(ctx: dict) -> dict:
    """arq cron entry point: purge expired data on a fixed schedule."""
    settings = get_settings()
    db = ctx["db_factory"]()
    try:
        return purge_expired_data(
            db,
            now=datetime.datetime.now(datetime.UTC),
            retention_days=settings.data_retention_days,
        )
    finally:
        db.close()
