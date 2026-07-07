"""Tests for retrying failed instant notification deliveries (ADR 0016)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.config import Settings
from pulsegraph.db.models import Analysis, Notification
from pulsegraph.domain.enums import (
    ModelKind,
    NotificationChannel,
    NotificationStatus,
)
from pulsegraph.pipeline.delivery import ChannelOutcome
from pulsegraph.worker.retry import retry_instant_notifications

_NOW = datetime.datetime(2026, 7, 7, 9, 0, tzinfo=datetime.UTC)


def _analysis(summary: str = "Update one") -> Analysis:
    return Analysis(
        id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        model_used=ModelKind.OLLAMA,
        model_version="llama3.1:8b",
        result=summary,
        confidence=0.9,
    )


def _pending(
    analysis_id: uuid.UUID,
    *,
    channel: NotificationChannel = NotificationChannel.EMAIL,
    key: str = "jobtech:1",
    attempts: int = 0,
    status: NotificationStatus = NotificationStatus.PENDING,
) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        analysis_id=analysis_id,
        channel=channel,
        dedup_key=key,
        status=status,
        delivered_at=None,
        attempts=attempts,
    )


class _DeliverSink:
    """Fake channel sink whose deliver() returns a fixed outcome."""

    def __init__(self, outcome: ChannelOutcome) -> None:
        self._outcome = outcome

    def deliver(self, draft: object) -> ChannelOutcome:
        return self._outcome


def _patch_sink(monkeypatch, sink) -> None:
    monkeypatch.setattr(
        "pulsegraph.worker.retry.build_channel_sink",
        lambda *args, **kwargs: sink,
    )


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_retry_marks_sent_on_success(monkeypatch) -> None:
    a = _analysis()
    n = _pending(a.id)
    db = FakeSession(a, n)
    _patch_sink(monkeypatch, _DeliverSink(ChannelOutcome.SENT))

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 1, "still_failing": 0, "dead_lettered": 0}
    assert n.status is NotificationStatus.SENT
    assert n.delivered_at == _NOW


def test_retry_increments_attempts_on_failure(monkeypatch) -> None:
    a = _analysis()
    n = _pending(a.id, attempts=0)
    db = FakeSession(a, n)
    _patch_sink(monkeypatch, _DeliverSink(ChannelOutcome.FAILED))

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 0, "still_failing": 1, "dead_lettered": 0}
    assert n.status is NotificationStatus.PENDING
    assert n.attempts == 1


def test_retry_dead_letters_at_cap(monkeypatch) -> None:
    # instant_max_attempts defaults to 5: a row at attempt 4 that fails
    # again has now failed 5 times and is dead-lettered instead of retried
    # forever against a broken destination.
    a = _analysis()
    n = _pending(a.id, attempts=4)
    db = FakeSession(a, n)
    _patch_sink(monkeypatch, _DeliverSink(ChannelOutcome.FAILED))

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 0, "still_failing": 1, "dead_lettered": 1}
    assert n.status is NotificationStatus.FAILED
    assert n.attempts == 5


def test_retry_dead_letters_when_user_disabled_channel(monkeypatch) -> None:
    # The user turned the channel off since the failed send, so the resolver
    # returns nothing (SKIPPED): the row can never be delivered and is
    # dead-lettered immediately rather than retried forever.
    a = _analysis()
    n = _pending(a.id, channel=NotificationChannel.WEBHOOK)
    db = FakeSession(a, n)
    _patch_sink(monkeypatch, _DeliverSink(ChannelOutcome.SKIPPED))

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 0, "still_failing": 0, "dead_lettered": 1}
    assert n.status is NotificationStatus.FAILED


def test_retry_ignores_dashboard_digest_queue(monkeypatch) -> None:
    # Digest PENDING rows are the dashboard channel; the digest job owns
    # them. The instant-retry job must leave them untouched.
    a = _analysis()
    digest_row = _pending(
        a.id, channel=NotificationChannel.DASHBOARD, key="jobtech:2"
    )
    email_row = _pending(a.id, channel=NotificationChannel.EMAIL)
    db = FakeSession(a, digest_row, email_row)
    _patch_sink(monkeypatch, _DeliverSink(ChannelOutcome.SENT))

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 1, "still_failing": 0, "dead_lettered": 0}
    assert email_row.status is NotificationStatus.SENT
    assert digest_row.status is NotificationStatus.PENDING


def test_retry_leaves_pending_when_channel_off_globally(monkeypatch) -> None:
    # build_channel_sink returns None when the channel is disabled globally;
    # the row stays PENDING to be retried once it is re-enabled.
    a = _analysis()
    n = _pending(a.id)
    db = FakeSession(a, n)
    _patch_sink(monkeypatch, None)

    result = retry_instant_notifications(db, _settings(), now=_NOW)

    assert result == {"resent": 0, "still_failing": 0, "dead_lettered": 0}
    assert n.status is NotificationStatus.PENDING


def test_retry_noop_without_pending() -> None:
    result = retry_instant_notifications(FakeSession(), _settings(), now=_NOW)
    assert result == {"resent": 0, "still_failing": 0, "dead_lettered": 0}
