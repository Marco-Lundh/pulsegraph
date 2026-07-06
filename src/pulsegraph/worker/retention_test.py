"""Tests for the GDPR data-retention purge job (ADR 0018)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import Item, PipelineRun
from pulsegraph.domain.enums import RunStatus, SourceKind
from pulsegraph.worker.retention import purge_expired_data, run_retention

_NOW = datetime.datetime(2026, 6, 28, tzinfo=datetime.UTC)


def _item(age_days: int) -> Item:
    return Item(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        watch_id=uuid.uuid4(),
        source=SourceKind.JOBTECH,
        raw_payload={},
        content_hash=str(uuid.uuid4()),
        fetched_at=_NOW - datetime.timedelta(days=age_days),
    )


def _run(age_days: int) -> PipelineRun:
    return PipelineRun(
        id=uuid.uuid4(),
        watch_id=uuid.uuid4(),
        status=RunStatus.SUCCEEDED,
        started_at=_NOW - datetime.timedelta(days=age_days),
    )


def test_purges_items_older_than_window() -> None:
    old, fresh = _item(120), _item(10)
    db = FakeSession(old, fresh)

    result = purge_expired_data(db, now=_NOW, retention_days=90)

    assert result["items"] == 1
    assert db.query(Item).all() == [fresh]


def test_purges_runs_older_than_window() -> None:
    old, fresh = _run(120), _run(10)
    db = FakeSession(old, fresh)

    result = purge_expired_data(db, now=_NOW, retention_days=90)

    assert result["runs"] == 1
    assert db.query(PipelineRun).all() == [fresh]


def test_keeps_everything_within_window() -> None:
    db = FakeSession(_item(10), _item(89), _run(30))

    result = purge_expired_data(db, now=_NOW, retention_days=90)

    assert result == {"items": 0, "runs": 0, "checkpoints": 0}
    assert len(db.query(Item).all()) == 2
    assert len(db.query(PipelineRun).all()) == 1


def test_item_at_exact_window_edge_is_kept() -> None:
    # Exactly retention_days old: not yet past the window, so retained.
    db = FakeSession(_item(90))

    result = purge_expired_data(db, now=_NOW, retention_days=90)

    assert result["items"] == 0


def test_run_retention_uses_settings_and_factory() -> None:
    db = FakeSession(_item(400), _run(400))
    ctx = {"db_factory": lambda: db}

    import asyncio

    result = asyncio.run(run_retention(ctx))

    # 400-day-old rows are well past the default 90-day window. No pipeline
    # deps in ctx, so there is no checkpointer to purge.
    assert result == {"items": 1, "runs": 1, "checkpoints": 0}


class _StubCheckpointer:
    """Records the thread ids whose checkpoints were deleted (ADR 0001)."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


def test_purges_checkpoints_for_expired_runs() -> None:
    old, fresh = _run(120), _run(10)
    db = FakeSession(old, fresh)
    checkpointer = _StubCheckpointer()

    result = purge_expired_data(
        db, now=_NOW, retention_days=90, checkpointer=checkpointer
    )

    assert result["checkpoints"] == 1
    # Only the expired run's checkpoints are cleared, keyed by run id.
    assert checkpointer.deleted == [str(old.id)]


def test_checkpoint_purge_is_a_noop_without_a_checkpointer() -> None:
    db = FakeSession(_run(120))

    result = purge_expired_data(db, now=_NOW, retention_days=90)

    assert result["checkpoints"] == 0
