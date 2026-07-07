"""Tests for /notifications, including per-channel settings (ADR 0016)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.db.models import Notification, NotificationSetting
from pulsegraph.domain.enums import (
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
)

_NOW = datetime.datetime(2026, 7, 7, 9, 0, tzinfo=datetime.UTC)


def _notif(
    user_id: uuid.UUID,
    channel: NotificationChannel,
    *,
    key: str = "jobtech:1",
    status: NotificationStatus = NotificationStatus.SENT,
    attempts: int = 0,
    delivered: bool = True,
) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        user_id=user_id,
        analysis_id=uuid.uuid4(),
        channel=channel,
        dedup_key=key,
        status=status,
        delivered_at=_NOW if delivered else None,
        attempts=attempts,
    )


# --- feed: list ---


def test_feed_shows_one_row_per_item_with_deliveries() -> None:
    client, user, _ = make_client()
    db = FakeSession(
        user,
        _notif(user.id, NotificationChannel.DASHBOARD),
        _notif(user.id, NotificationChannel.EMAIL),
        _notif(
            user.id,
            NotificationChannel.WEBHOOK,
            status=NotificationStatus.PENDING,
            attempts=2,
            delivered=False,
        ),
    )
    client2, _, _ = make_client(db=db, user=user)

    body = client2.get("/notifications").json()

    # One feed row for the item (the dashboard channel), not three.
    assert len(body) == 1
    row = body[0]
    assert row["channel"] == "dashboard"
    deliveries = {d["channel"]: d for d in row["deliveries"]}
    assert deliveries["email"]["status"] == "sent"
    assert deliveries["webhook"]["status"] == "pending"
    assert deliveries["webhook"]["attempts"] == 2


def test_feed_item_without_side_channels_has_empty_deliveries() -> None:
    client, user, _ = make_client()
    db = FakeSession(user, _notif(user.id, NotificationChannel.DASHBOARD))
    client2, _, _ = make_client(db=db, user=user)

    body = client2.get("/notifications").json()

    assert len(body) == 1
    assert body[0]["deliveries"] == []


def test_feed_excludes_other_users() -> None:
    client, user, _ = make_client()
    db = FakeSession(
        user,
        _notif(user.id, NotificationChannel.DASHBOARD, key="jobtech:1"),
        _notif(uuid.uuid4(), NotificationChannel.DASHBOARD, key="jobtech:9"),
    )
    client2, _, _ = make_client(db=db, user=user)

    body = client2.get("/notifications").json()

    assert len(body) == 1
    assert body[0]["dedup_key"] == "jobtech:1"


# --- settings: list ---


def test_list_settings_empty() -> None:
    client, _, _ = make_client()
    resp = client.get("/notifications/settings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_settings_returns_only_own() -> None:
    client, user, _ = make_client()
    own = NotificationSetting(
        user_id=user.id,
        channel=NotificationChannel.EMAIL,
        frequency=NotificationFrequency.INSTANT,
        destination=None,
        is_active=True,
    )
    other = NotificationSetting(
        user_id=uuid.uuid4(),
        channel=NotificationChannel.EMAIL,
        frequency=NotificationFrequency.INSTANT,
        destination=None,
        is_active=True,
    )
    db = FakeSession(user, own, other)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.get("/notifications/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["channel"] == "email"


# --- settings: upsert ---


def test_put_settings_creates_new_row() -> None:
    client, _, _ = make_client()
    resp = client.put(
        "/notifications/settings/email",
        json={"frequency": "instant", "is_active": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["channel"] == "email"
    assert body["frequency"] == "instant"
    assert body["is_active"] is True
    assert body["destination"] is None


def test_put_settings_updates_existing_row() -> None:
    client, user, _ = make_client()
    existing = NotificationSetting(
        user_id=user.id,
        channel=NotificationChannel.EMAIL,
        frequency=NotificationFrequency.INSTANT,
        destination=None,
        is_active=True,
    )
    db = FakeSession(user, existing)
    client2, _, _ = make_client(db=db, user=user)
    resp = client2.put(
        "/notifications/settings/email",
        json={
            "frequency": "daily_digest",
            "destination": "me@example.com",
            "is_active": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["frequency"] == "daily_digest"
    assert body["destination"] == "me@example.com"
    assert body["is_active"] is False
    # Same row was mutated, not duplicated.
    assert len(db._store[NotificationSetting]) == 1


def test_put_settings_dashboard_channel_rejected() -> None:
    client, _, _ = make_client()
    resp = client.put(
        "/notifications/settings/dashboard",
        json={"frequency": "instant", "is_active": True},
    )
    assert resp.status_code == 400


def test_put_settings_webhook_requires_destination_when_active() -> None:
    client, _, _ = make_client()
    resp = client.put(
        "/notifications/settings/webhook",
        json={"frequency": "instant", "is_active": True},
    )
    assert resp.status_code == 422


def test_put_settings_webhook_with_destination_ok() -> None:
    client, _, _ = make_client()
    resp = client.put(
        "/notifications/settings/webhook",
        json={
            "frequency": "instant",
            "destination": "https://example.com/hook",
            "is_active": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["destination"] == "https://example.com/hook"


def test_put_settings_webhook_inactive_allows_missing_destination() -> None:
    client, _, _ = make_client()
    resp = client.put(
        "/notifications/settings/webhook",
        json={"frequency": "instant", "is_active": False},
    )
    assert resp.status_code == 200
