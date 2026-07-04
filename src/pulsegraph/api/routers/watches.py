"""Watch CRUD endpoints — tenant-scoped (ADR 0005/0008/0021)."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.schemas import WatchCreate, WatchOut, WatchUpdate
from pulsegraph.config import get_settings
from pulsegraph.db.models import AuditLogEntry, User, Watch

router = APIRouter(prefix="/watches", tags=["watches"])


def _audit(
    db: Session, actor_id: object, action: str, entity_id: object
) -> None:
    db.add(
        AuditLogEntry(
            actor_user_id=actor_id,
            action=action,
            entity_type="watch",
            entity_id=entity_id,
            meta={},
        )
    )


def _get_own_watch(
    db: Session, watch_id: uuid.UUID, user_id: uuid.UUID
) -> Watch:
    watch = db.get(Watch, watch_id)
    if watch is None or watch.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return watch


@router.get("", response_model=list[WatchOut])
def list_watches(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Watch]:
    # FakeSession.filter() is a no-op in tests, so re-filter in Python too
    # (mirrors the pattern used throughout worker/*.py).
    rows = [
        w
        for w in db.query(Watch).filter(Watch.user_id == user.id).all()
        if w.user_id == user.id
    ]
    return [WatchOut.from_orm(w) for w in rows]


@router.post("", response_model=WatchOut, status_code=status.HTTP_201_CREATED)
def create_watch(
    body: WatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    limit = get_settings().max_active_watches_per_user
    active = sum(
        1
        for w in db.query(Watch)
        .filter(Watch.user_id == user.id, Watch.is_active.is_(True))
        .all()
        if w.user_id == user.id and w.is_active
    )
    if active >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Active watch limit ({limit}) reached",
        )
    now = datetime.datetime.now(datetime.UTC)
    watch = Watch(
        user_id=user.id,
        source=body.source,
        prompt=body.prompt,
        config=body.config,
        is_active=True,
        schedule_interval=datetime.timedelta(
            seconds=body.schedule_interval_seconds
        ),
        next_run_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(watch)
    db.flush()
    _audit(db, user.id, "watch.create", watch.id)
    db.commit()
    db.refresh(watch)
    return WatchOut.from_orm(watch)


@router.get("/{watch_id}", response_model=WatchOut)
def get_watch(
    watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    return WatchOut.from_orm(_get_own_watch(db, watch_id, user.id))


@router.patch("/{watch_id}", response_model=WatchOut)
def update_watch(
    watch_id: uuid.UUID,
    body: WatchUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WatchOut:
    watch = _get_own_watch(db, watch_id, user.id)
    if body.prompt is not None:
        watch.prompt = body.prompt
    if body.config is not None:
        watch.config = body.config
    if body.is_active is not None:
        watch.is_active = body.is_active
    if body.schedule_interval_seconds is not None:
        watch.schedule_interval = datetime.timedelta(
            seconds=body.schedule_interval_seconds
        )
    watch.updated_at = datetime.datetime.now(datetime.UTC)
    _audit(db, user.id, "watch.update", watch.id)
    db.commit()
    db.refresh(watch)
    return WatchOut.from_orm(watch)


@router.delete("/{watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watch(
    watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    watch = _get_own_watch(db, watch_id, user.id)
    watch.is_active = False
    _audit(db, user.id, "watch.delete", watch.id)
    db.commit()
