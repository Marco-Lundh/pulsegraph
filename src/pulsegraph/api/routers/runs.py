"""Pipeline run history — tenant-scoped (ADR 0007/0015)."""

import datetime
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.schemas import RunOut
from pulsegraph.db.models import PipelineRun, User, Watch

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(
    watch_id: uuid.UUID | None = None,
    since: datetime.datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PipelineRun]:
    """List the caller's pipeline runs, optionally scoped to a watch.

    ``since`` bounds the result to runs started on or after that instant
    (e.g. a 7-day dashboard chart), so callers don't have to pull the
    caller's entire run history on every poll.
    """
    # Scope to the authenticated user's watches only. Filtered in Python
    # too, so it is correct under the FakeSession test double whose
    # filter is a no-op.
    user_watch_ids = {
        w.id
        for w in db.query(Watch).filter(Watch.user_id == user.id).all()
        if w.user_id == user.id
    }
    q = db.query(PipelineRun).filter(PipelineRun.watch_id.in_(user_watch_ids))
    if watch_id is not None:
        q = q.filter(PipelineRun.watch_id == watch_id)
    if since is not None:
        q = q.filter(PipelineRun.started_at >= since)
    runs = q.order_by(PipelineRun.started_at.desc()).all()
    runs = [r for r in runs if r.watch_id in user_watch_ids]
    if watch_id is not None:
        runs = [r for r in runs if r.watch_id == watch_id]
    if since is not None:
        runs = [r for r in runs if r.started_at >= since]
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return runs
