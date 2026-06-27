"""Pipeline run history — tenant-scoped (ADR 0007/0015)."""

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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PipelineRun]:
    # Scope to the authenticated user's watches only.
    user_watch_ids = [
        w.id for w in db.query(Watch.id).filter(Watch.user_id == user.id).all()
    ]
    q = db.query(PipelineRun).filter(PipelineRun.watch_id.in_(user_watch_ids))
    if watch_id is not None:
        q = q.filter(PipelineRun.watch_id == watch_id)
    return q.order_by(PipelineRun.started_at.desc()).all()
