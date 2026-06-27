"""Tests for select_due_watches (ADR 0015)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import SourceHealth, Watch
from pulsegraph.domain.enums import SourceKind, SourceStatus
from pulsegraph.worker.scheduler import select_due_watches

_NOW = datetime.datetime.now(datetime.UTC)
_PAST = _NOW - datetime.timedelta(hours=1)
_FUTURE = _NOW + datetime.timedelta(hours=1)


def _watch(
    source: SourceKind = SourceKind.JOBTECH,
    is_active: bool = True,
    next_run_at: datetime.datetime = _PAST,
) -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        source=source,
        prompt="test",
        config={},
        is_active=is_active,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=next_run_at,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _paused_source(source: SourceKind) -> SourceHealth:
    return SourceHealth(
        source=source,
        status=SourceStatus.PAUSED,
        last_checked_at=_NOW,
    )


def test_returns_due_active_watch() -> None:
    w = _watch()
    db = FakeSession(w)
    result = select_due_watches(db)
    assert result == [w]


def test_skips_inactive_watch() -> None:
    w = _watch(is_active=False)
    db = FakeSession(w)
    assert select_due_watches(db) == []


def test_skips_future_watch() -> None:
    w = _watch(next_run_at=_FUTURE)
    db = FakeSession(w)
    assert select_due_watches(db) == []


def test_skips_paused_source() -> None:
    w = _watch(source=SourceKind.JOBTECH)
    paused = _paused_source(SourceKind.JOBTECH)
    db = FakeSession(w, paused)
    assert select_due_watches(db) == []


def test_healthy_source_is_included() -> None:
    w = _watch(source=SourceKind.RIKSDAGEN)
    paused = _paused_source(SourceKind.JOBTECH)  # different source paused
    db = FakeSession(w, paused)
    assert select_due_watches(db) == [w]


def test_multiple_due_watches_all_returned() -> None:
    watches = [_watch() for _ in range(3)]
    db = FakeSession(*watches)
    assert len(select_due_watches(db)) == 3
