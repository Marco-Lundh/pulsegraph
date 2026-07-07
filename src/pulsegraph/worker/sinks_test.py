"""Tests for per-run notification sink assembly (ADR 0016)."""

import types
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import NotificationSetting, User
from pulsegraph.domain.enums import (
    NotificationChannel,
    NotificationFrequency,
    UserRole,
)
from pulsegraph.pipeline.delivery import EmailSink, MultiSink, WebhookSink
from pulsegraph.worker.sinks import (
    _destination_resolver,
    build_channel_sink,
    build_notification_sink,
)

_INSTANT = NotificationFrequency.INSTANT
_DIGEST = NotificationFrequency.DAILY_DIGEST


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
        frequency=_INSTANT,
        is_active=True,
    )
    db = FakeSession(setting)

    resolve = _destination_resolver(db, NotificationChannel.WEBHOOK, _INSTANT)

    assert resolve(str(uid)) == "https://hook.example/x"


def test_resolver_falls_back_to_account_email() -> None:
    uid = uuid.uuid4()
    setting = NotificationSetting(
        user_id=uid,
        channel=NotificationChannel.EMAIL,
        destination=None,
        frequency=_INSTANT,
        is_active=True,
    )
    user = User(
        id=uid,
        email="user@example.com",
        password_hash="x",
        role=UserRole.USER,
    )
    db = FakeSession(setting, user)

    resolve = _destination_resolver(db, NotificationChannel.EMAIL, _INSTANT)

    assert resolve(str(uid)) == "user@example.com"


def test_resolver_returns_none_without_setting() -> None:
    db = FakeSession()

    resolve = _destination_resolver(db, NotificationChannel.WEBHOOK, _INSTANT)

    assert resolve(str(uuid.uuid4())) is None


def test_resolver_does_not_leak_other_users_setting() -> None:
    # FakeSession.filter() is a no-op, so the re-filter must also check
    # user_id/channel/is_active, not just frequency — otherwise the first
    # matching-frequency row in the whole store wins, leaking across users.
    user_a = uuid.uuid4()
    user_b_setting = NotificationSetting(
        user_id=uuid.uuid4(),
        channel=NotificationChannel.WEBHOOK,
        destination="https://user-b.example/hook",
        frequency=_INSTANT,
        is_active=True,
    )
    user_a_setting = NotificationSetting(
        user_id=user_a,
        channel=NotificationChannel.EMAIL,
        destination=None,
        frequency=_INSTANT,
        is_active=True,
    )
    user_a_account = User(
        id=user_a,
        email="user-a@example.com",
        password_hash="x",
        role=UserRole.USER,
    )
    db = FakeSession(user_b_setting, user_a_setting, user_a_account)

    resolve = _destination_resolver(db, NotificationChannel.EMAIL, _INSTANT)

    assert resolve(str(user_a)) == "user-a@example.com"


def test_resolver_skips_setting_of_other_frequency() -> None:
    uid = uuid.uuid4()
    setting = NotificationSetting(
        user_id=uid,
        channel=NotificationChannel.WEBHOOK,
        destination="https://hook.example/x",
        frequency=_DIGEST,
        is_active=True,
    )
    db = FakeSession(setting)

    # The instant resolver must not match a digest subscription.
    instant = _destination_resolver(db, NotificationChannel.WEBHOOK, _INSTANT)
    digest = _destination_resolver(db, NotificationChannel.WEBHOOK, _DIGEST)

    assert instant(str(uid)) is None
    assert digest(str(uid)) == "https://hook.example/x"


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


# --- build_channel_sink ----------------------------------------------------


def test_build_channel_sink_returns_email_sink_when_enabled() -> None:
    sink = build_channel_sink(
        _settings(email_enabled=True),
        FakeSession(),
        NotificationChannel.EMAIL,
    )
    assert isinstance(sink, EmailSink)


def test_build_channel_sink_returns_webhook_sink_when_enabled() -> None:
    sink = build_channel_sink(
        _settings(webhook_enabled=True),
        FakeSession(),
        NotificationChannel.WEBHOOK,
    )
    assert isinstance(sink, WebhookSink)


def test_build_channel_sink_returns_none_when_channel_off() -> None:
    # email disabled globally -> no sink to retry on
    assert (
        build_channel_sink(
            _settings(), FakeSession(), NotificationChannel.EMAIL
        )
        is None
    )


def test_build_channel_sink_returns_none_for_dashboard() -> None:
    # Dashboard is not a retryable outbound channel.
    assert (
        build_channel_sink(
            _settings(email_enabled=True, webhook_enabled=True),
            FakeSession(),
            NotificationChannel.DASHBOARD,
        )
        is None
    )
