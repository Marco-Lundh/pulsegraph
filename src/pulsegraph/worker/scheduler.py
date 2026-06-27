"""Watch scheduling: select due watches and enqueue pipeline jobs (ADR 0015)."""

import datetime

from sqlalchemy.orm import Session

from pulsegraph.db.models import SourceHealth, Watch
from pulsegraph.domain.enums import SourceStatus


def select_due_watches(db: Session) -> list[Watch]:
    """Return active watches that are due now, on a healthy source.

    Excludes watches whose source is currently paused (ADR 0010).
    """
    now = datetime.datetime.now(datetime.UTC)
    paused = {
        row.source
        for row in db.query(SourceHealth)
        .filter(SourceHealth.status == SourceStatus.PAUSED)
        .all()
    }
    # DB query narrows the candidate set in production; the Python guard
    # ensures correctness with test doubles that ignore filter expressions.
    candidates = (
        db.query(Watch)
        .filter(Watch.is_active.is_(True), Watch.next_run_at <= now)
        .all()
    )
    return [
        w
        for w in candidates
        if w.is_active and w.next_run_at <= now and w.source not in paused
    ]


async def enqueue_due_watches(ctx: dict) -> dict:
    """arq cron entry point: enqueue a run_watch job for every due watch.

    Called on a fixed schedule (see WorkerSettings). The actual pipeline
    runs in separate worker processes so the scheduler stays lightweight.
    """
    from arq import ArqRedis

    db = ctx["db_factory"]()
    try:
        watches = select_due_watches(db)
    finally:
        db.close()

    redis: ArqRedis = ctx["redis"]
    for watch in watches:
        await redis.enqueue_job("run_watch", str(watch.id))

    return {"enqueued": len(watches)}
