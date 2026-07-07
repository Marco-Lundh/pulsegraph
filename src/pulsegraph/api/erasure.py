"""GDPR erasure that reaches the graph checkpointer (ADR 0001/0018).

Deleting a user cascades every user-owned row via ON DELETE CASCADE, but
the LangGraph checkpoint tables are the saver's own — keyed by the run id
that was each run's ``thread_id`` and not FK-linked to ``pipeline_runs`` —
so a cascade never touches them. The scheduled retention job purges an
expired run's checkpoints, but immediate erasure must reach them too, or a
just-erased user's fetched content and watch queries would live on in the
checkpoints until the next retention pass. This closes that gap.

Must be called *before* the user (and thus their runs) is deleted, while
the run ids are still queryable — mirroring the retention job, which purges
each expired run's checkpoints before deleting the run rows. The checkpoint
delete runs on the saver's own (autocommit) connection, so it is
best-effort and independent of the request transaction — a partial failure
errs toward deleting more, never leaking data.
"""

import uuid

from sqlalchemy.orm import Session

from pulsegraph.db.models import PipelineRun, Watch
from pulsegraph.pipeline.checkpointer import delete_threads


def purge_user_checkpoints(
    db: Session, user_id: uuid.UUID, checkpointer: object
) -> int:
    """Delete the graph checkpoints of every run owned by ``user_id``.

    Best-effort and a no-op (returns 0) when no durable checkpointer is
    configured. Runs are reached through the user's watches
    (``PipelineRun`` has no direct ``user_id``). FakeSession.filter() is a
    no-op, so ownership is re-checked in Python too (mirrors the pattern
    used across worker/* and the other tenant-scoped queries).
    """
    watch_ids = {
        w.id
        for w in db.query(Watch).filter(Watch.user_id == user_id).all()
        if w.user_id == user_id
    }
    if not watch_ids:
        return 0
    thread_ids = [
        str(run.id)
        for run in db.query(PipelineRun)
        .filter(PipelineRun.watch_id.in_(watch_ids))
        .all()
        if run.watch_id in watch_ids
    ]
    return delete_threads(checkpointer, thread_ids)
