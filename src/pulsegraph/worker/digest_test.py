"""Tests for daily notification digest batching (ADR 0016)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.config import Settings
from pulsegraph.db.models import Analysis, Notification, NotificationSetting
from pulsegraph.domain.enums import (
    ModelKind,
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
)
from pulsegraph.pipeline.delivery import DeliveryResult
from pulsegraph.worker.digest import (
    build_digest_draft,
    send_digests,
    user_wants_digest,
)

_NOW = datetime.datetime(2026, 6, 28, 6, 0, tzinfo=datetime.UTC)


def _setting(
    uid: uuid.UUID,
    frequency: NotificationFrequency,
    channel: NotificationChannel = NotificationChannel.EMAIL,
) -> NotificationSetting:
    return NotificationSetting(
        user_id=uid,
        channel=channel,
        frequency=frequency,
        destination="x@example.com",
        is_active=True,
    )


def _pending(
    uid: uuid.UUID, analysis_id: uuid.UUID, key: str, attempts: int = 0
) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        user_id=uid,
        analysis_id=analysis_id,
        channel=NotificationChannel.DASHBOARD,
        dedup_key=key,
        status=NotificationStatus.PENDING,
        delivered_at=None,
        attempts=attempts,
    )


def _analysis(summary: str) -> Analysis:
    return Analysis(
        id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        model_used=ModelKind.OLLAMA,
        model_version="llama3.1:8b",
        result=summary,
        confidence=0.9,
    )


# --- user_wants_digest -----------------------------------------------------


def test_user_wants_digest_true_for_digest_only() -> None:
    uid = uuid.uuid4()
    db = FakeSession(_setting(uid, NotificationFrequency.DAILY_DIGEST))
    assert user_wants_digest(db, uid) is True


def test_user_wants_digest_false_for_instant() -> None:
    uid = uuid.uuid4()
    db = FakeSession(_setting(uid, NotificationFrequency.INSTANT))
    assert user_wants_digest(db, uid) is False


def test_user_wants_digest_false_without_settings() -> None:
    db = FakeSession()
    assert user_wants_digest(db, uuid.uuid4()) is False


def test_user_wants_digest_false_when_mixed_with_instant() -> None:
    uid = uuid.uuid4()
    db = FakeSession(
        _setting(uid, NotificationFrequency.DAILY_DIGEST),
        _setting(
            uid, NotificationFrequency.INSTANT, NotificationChannel.WEBHOOK
        ),
    )
    assert user_wants_digest(db, uid) is False


# --- build_digest_draft ----------------------------------------------------


def test_build_digest_draft_combines_summaries() -> None:
    uid = str(uuid.uuid4())
    draft = build_digest_draft(uid, ["First update", "Second update"], _NOW)
    assert "2 updates" in draft.title
    assert "First update" in draft.body
    assert "Second update" in draft.body
    assert draft.dedup_key == f"digest:{uid}:2026-06-28"


def test_build_digest_draft_singular_for_one() -> None:
    draft = build_digest_draft(str(uuid.uuid4()), ["Only one"], _NOW)
    assert "1 update" in draft.title
    assert "updates" not in draft.title


# --- send_digests ----------------------------------------------------------


def test_send_digests_batches_and_marks_sent() -> None:
    uid = uuid.uuid4()
    a1, a2 = _analysis("Update one"), _analysis("Update two")
    n1 = _pending(uid, a1.id, "jobtech:1")
    n2 = _pending(uid, a2.id, "jobtech:2")
    db = FakeSession(a1, a2, n1, n2)

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 1,
        "notifications": 2,
        "failed_users": 0,
        "dead_lettered": 0,
    }
    assert n1.status == NotificationStatus.SENT
    assert n1.delivered_at == _NOW
    assert n2.status == NotificationStatus.SENT


def test_send_digests_noop_without_pending() -> None:
    db = FakeSession()
    result = send_digests(db, Settings(_env_file=None), now=_NOW)
    assert result == {
        "users": 0,
        "notifications": 0,
        "failed_users": 0,
        "dead_lettered": 0,
    }


class _FailingSink:
    """Every channel fails: simulates a fully, permanently broken user."""

    def send_detailed(self, draft: object) -> DeliveryResult:
        return DeliveryResult(all_ok=False, any_ok=False)


def test_send_digests_leaves_pending_on_delivery_failure(monkeypatch) -> None:
    # A failed push must NOT be marked SENT — otherwise the notification
    # is lost forever instead of being retried on the next scheduled run.
    uid = uuid.uuid4()
    a1 = _analysis("Update one")
    n1 = _pending(uid, a1.id, "jobtech:1")
    db = FakeSession(a1, n1)
    monkeypatch.setattr(
        "pulsegraph.worker.digest.build_notification_sink",
        lambda *args, **kwargs: _FailingSink(),
    )

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 1,
        "notifications": 0,
        "failed_users": 1,
        "dead_lettered": 0,
    }
    assert n1.status == NotificationStatus.PENDING
    assert n1.delivered_at is None
    assert n1.attempts == 1


def test_send_digests_only_retries_the_failed_user(monkeypatch) -> None:
    ok_uid, failing_uid = uuid.uuid4(), uuid.uuid4()
    a_ok, a_fail = _analysis("Update one"), _analysis("Update two")
    n_ok = _pending(ok_uid, a_ok.id, "jobtech:1")
    n_fail = _pending(failing_uid, a_fail.id, "jobtech:2")
    db = FakeSession(a_ok, a_fail, n_ok, n_fail)

    class _PerUserSink:
        def send_detailed(self, draft) -> DeliveryResult:
            ok = str(failing_uid) not in draft.user_id
            return DeliveryResult(all_ok=ok, any_ok=ok)

    monkeypatch.setattr(
        "pulsegraph.worker.digest.build_notification_sink",
        lambda *args, **kwargs: _PerUserSink(),
    )

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 2,
        "notifications": 1,
        "failed_users": 1,
        "dead_lettered": 0,
    }
    assert n_ok.status == NotificationStatus.SENT
    assert n_fail.status == NotificationStatus.PENDING
    assert n_fail.attempts == 1


# --- retry cap / dead-letter ------------------------------------------------


def test_send_digests_dead_letters_after_max_attempts(monkeypatch) -> None:
    # digest_max_attempts defaults to 5 (see Settings). A notification
    # already at attempt 4 that fails again this run has now failed 5
    # times total, so it must be dead-lettered instead of retried forever.
    uid = uuid.uuid4()
    a1 = _analysis("Update one")
    n1 = _pending(uid, a1.id, "jobtech:1", attempts=4)
    db = FakeSession(a1, n1)
    monkeypatch.setattr(
        "pulsegraph.worker.digest.build_notification_sink",
        lambda *args, **kwargs: _FailingSink(),
    )

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 1,
        "notifications": 0,
        "failed_users": 1,
        "dead_lettered": 1,
    }
    assert n1.status == NotificationStatus.FAILED
    assert n1.attempts == 5


class _PartialSink:
    """One channel ok, one broken: destination is not fully dead."""

    def send_detailed(self, draft: object) -> DeliveryResult:
        return DeliveryResult(all_ok=False, any_ok=True)


def test_send_digests_partial_success_does_not_count_toward_cap(
    monkeypatch,
) -> None:
    # A user with e.g. a working email channel and a broken webhook
    # channel must never be dead-lettered on the working channel just
    # because the batch isn't fully delivered (see the module docstring's
    # "duplicate, never lost" trade-off).
    uid = uuid.uuid4()
    a1 = _analysis("Update one")
    n1 = _pending(uid, a1.id, "jobtech:1", attempts=4)
    db = FakeSession(a1, n1)
    monkeypatch.setattr(
        "pulsegraph.worker.digest.build_notification_sink",
        lambda *args, **kwargs: _PartialSink(),
    )

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 1,
        "notifications": 0,
        "failed_users": 1,
        "dead_lettered": 0,
    }
    assert n1.status == NotificationStatus.PENDING
    assert n1.attempts == 4


def test_send_digests_dead_lettered_row_not_retried_again(monkeypatch) -> None:
    # Once a notification is dead-lettered it is no longer PENDING, so the
    # next scheduled run must not pick it up again.
    uid = uuid.uuid4()
    a1 = _analysis("Update one")
    n1 = _pending(uid, a1.id, "jobtech:1", attempts=4)
    db = FakeSession(a1, n1)
    monkeypatch.setattr(
        "pulsegraph.worker.digest.build_notification_sink",
        lambda *args, **kwargs: _FailingSink(),
    )
    send_digests(db, Settings(_env_file=None), now=_NOW)

    result = send_digests(db, Settings(_env_file=None), now=_NOW)

    assert result == {
        "users": 0,
        "notifications": 0,
        "failed_users": 0,
        "dead_lettered": 0,
    }
