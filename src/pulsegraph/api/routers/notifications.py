"""Notification endpoints — tenant-scoped (ADR 0016)."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.schemas import NotificationOut
from pulsegraph.db.models import Notification, User
from pulsegraph.domain.enums import NotificationStatus

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Notification]:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.delivered_at.desc())
        .all()
    )


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Notification:
    notif = db.get(Notification, notification_id)
    if notif is None or notif.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    notif.status = NotificationStatus.SENT
    notif.delivered_at = datetime.datetime.now(datetime.UTC)
    db.commit()
    db.refresh(notif)
    return notif
