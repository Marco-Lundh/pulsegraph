"""Tests for per-run notification sink assembly (ADR 0016)."""

import types
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import NotificationSetting, User
from pulsegraph.domain.enums import NotificationChannel, UserRole
from pulsegraph.pipeline.delivery import MultiSink
from pulsegraph.worker.sinks import (
    _destination_resolver,
    build_notification_sink,
)


def _settings(**overrides) -> types.SimpleNamespace:
    base = {
        "email_enabled": False,
        "email_from": "alerts@pulsegraph.io",
        "smtp_host": "localhost",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_use_tls": True,
        "webhook_enabled": False,
        "webhook_signing_secret": "",
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


# --- _destination_resolver -------------------------------------------------


def test_resolver_returns_explicit_destination() -> None:
    uid = uuid.uuid4()
    setting = NotificationSetting(
        user_id=uid,
        channel=NotificationChannel.WEBHOOK,
        destination="https://hook.example/x",
        is_active=True,
    )
    db = FakeSession(setting)

    resolve = _destination_resolver(db, NotificationChannel.WEBHOOK)

    assert resolve(str(uid)) == "https://hook.example/x"


def test_resolver_falls_back_to_account_email() -> None:
    uid = uuid.uuid4()
    setting = NotificationSetting(
        user_id=uid,
        channel=NotificationChannel.EMAIL,
        destination=None,
        is_active=True,
    )
    user = User(
        id=uid,
        email="user@example.com",
        password_hash="x",
        role=UserRole.USER,
    )
    db = FakeSession(setting, user)

    resolve = _destination_resolver(db, NotificationChannel.EMAIL)

    assert resolve(str(uid)) == "user@example.com"


def test_resolver_returns_none_without_setting() -> None:
    db = FakeSession()

    resolve = _destination_resolver(db, NotificationChannel.WEBHOOK)

    assert resolve(str(uuid.uuid4())) is None


# --- build_notification_sink -----------------------------------------------


def test_builds_both_channels_when_enabled() -> None:
    sink = build_notification_sink(
        _settings(email_enabled=True, webhook_enabled=True),
        FakeSession(),
    )

    assert isinstance(sink, MultiSink)
    assert len(sink._sinks) == 2


def test_builds_no_channels_by_default() -> None:
    sink = build_notification_sink(_settings(), FakeSession())

    assert isinstance(sink, MultiSink)
    assert sink._sinks == ()
