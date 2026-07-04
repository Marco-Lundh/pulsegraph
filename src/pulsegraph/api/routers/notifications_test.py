"""Tests for /notifications, including per-channel settings (ADR 0016)."""

import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.db.models import NotificationSetting
from pulsegraph.domain.enums import NotificationChannel, NotificationFrequency

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
