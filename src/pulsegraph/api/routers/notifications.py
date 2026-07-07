"""Notification endpoints — tenant-scoped (ADR 0016)."""

import datetime
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from pulsegraph.api.deps import get_current_user, get_db
from pulsegraph.api.schemas import (
    DeliveryOut,
    NotificationOut,
    NotificationSettingOut,
    NotificationSettingUpdate,
)
from pulsegraph.db.models import Notification, NotificationSetting, User
from pulsegraph.domain.enums import NotificationChannel, NotificationStatus

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    """The in-app feed: one row per item (the dashboard channel).

    Each item is delivered on several channels (dashboard, email, webhook),
    each its own ``Notification`` row (ADR 0016). The feed shows only the
    dashboard row so an item appears once, enriched with the per-channel
    delivery status of its email/webhook sibling rows. FakeSession.filter()
    is a no-op in tests, so re-filter ownership in Python too.
    """
    rows = [
        n
        for n in db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.delivered_at.desc())
        .all()
        if n.user_id == user.id
    ]
    siblings: dict[str, list[Notification]] = defaultdict(list)
    for row in rows:
        if row.channel is not NotificationChannel.DASHBOARD:
            siblings[row.dedup_key].append(row)

    feed: list[NotificationOut] = []
    for row in rows:
        if row.channel is not NotificationChannel.DASHBOARD:
            continue
        out = NotificationOut.model_validate(row)
        out.deliveries = [
            DeliveryOut.model_validate(s)
            for s in siblings.get(row.dedup_key, [])
        ]
        feed.append(out)
    return feed


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


# ---------------------------------------------------------------------------
# Per-channel delivery settings (ADR 0016). Only EMAIL and WEBHOOK are
# user-configurable; DASHBOARD delivery is unconditional (see
# worker/persistence.py) and has no row here.
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=list[NotificationSettingOut])
def list_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationSetting]:
    # FakeSession.filter() is a no-op in tests, so re-filter in Python too
    # (mirrors the pattern used throughout worker/*.py).
    return [
        s
        for s in db.query(NotificationSetting)
        .filter(NotificationSetting.user_id == user.id)
        .all()
        if s.user_id == user.id
    ]


@router.put("/settings/{channel}", response_model=NotificationSettingOut)
def update_setting(
    channel: NotificationChannel,
    body: NotificationSettingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSetting:
    if channel is NotificationChannel.DASHBOARD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dashboard delivery cannot be configured",
        )
    if (
        channel is NotificationChannel.WEBHOOK
        and body.is_active
        and not body.destination
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook needs a destination URL to be active",
        )

    existing = next(
        (
            s
            for s in db.query(NotificationSetting)
            .filter(NotificationSetting.user_id == user.id)
            .all()
            if s.user_id == user.id and s.channel == channel
        ),
        None,
    )
    if existing is not None:
        existing.frequency = body.frequency
        existing.destination = body.destination
        existing.is_active = body.is_active
        setting = existing
    else:
        setting = NotificationSetting(
            user_id=user.id,
            channel=channel,
            frequency=body.frequency,
            destination=body.destination,
            is_active=body.is_active,
        )
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting
