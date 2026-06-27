"""Tests for run_watch_core and rate-limit logic (ADR 0015)."""

import datetime
import uuid

import fakeredis

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import PipelineRun, Watch
from pulsegraph.domain.enums import RunStatus, SourceKind
from pulsegraph.pipeline.agents import PipelineDeps
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
    StaticSourcePlugin,
)
from pulsegraph.worker.tasks import run_watch_core

_NOW = datetime.datetime.now(datetime.UTC)
_USER_ID = uuid.uuid4()


def _watch(user_id: uuid.UUID = _USER_ID) -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=user_id,
        source=SourceKind.JOBTECH,
        prompt="python",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _deps(records: list[dict] | None = None) -> PipelineDeps:
    registry = DictSourceRegistry()
    registry.register(StaticSourcePlugin(SourceKind.JOBTECH, records or []))
    return PipelineDeps(
        registry=registry,
        embedder=HashingEmbedder(),
        model=KeywordModelClient(keywords=("python",)),
        sink=InMemorySink(),
        cloud_available=False,
    )


def _redis(limit: int = 60) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


# ---------------------------------------------------------------------------
# Rate-limit tests
# ---------------------------------------------------------------------------


def test_rate_limit_allows_first_run() -> None:
    watch = _watch()
    db = FakeSession(watch)
    r = _redis()
    result = run_watch_core(db, watch, _deps(), r)
    assert "run_id" in result


def test_rate_limit_blocks_when_exceeded() -> None:
    watch = _watch()
    db = FakeSession(watch)
    r = _redis()
    # Exhaust the default limit of 60 by calling check_rate directly
    from pulsegraph.redis_client import check_rate

    for _ in range(60):
        check_rate(r, watch.user_id, limit=60)
    result = run_watch_core(db, watch, _deps(), r)
    assert result["skipped"] == "rate_limit"


def test_rate_limit_not_enforced_without_redis() -> None:
    watch = _watch()
    db = FakeSession(watch)
    result = run_watch_core(db, watch, _deps(), redis_client=None)
    assert "run_id" in result


# ---------------------------------------------------------------------------
# run_watch_core tests
# ---------------------------------------------------------------------------


def test_run_watch_core_succeeds_empty_source() -> None:
    watch = _watch()
    db = FakeSession(watch)
    result = run_watch_core(db, watch, _deps())
    assert "run_id" in result
    assert result["items"] == 0


def test_run_watch_core_updates_watch_schedule() -> None:
    watch = _watch()
    original_next = watch.next_run_at
    db = FakeSession(watch)
    run_watch_core(db, watch, _deps())
    assert watch.last_run_at is not None
    assert watch.next_run_at > original_next


def test_run_watch_core_creates_run_record() -> None:
    watch = _watch()
    db = FakeSession(watch)
    run_watch_core(db, watch, _deps())
    runs = db.query(PipelineRun).all()
    assert len(runs) == 1
    assert runs[0].status == RunStatus.SUCCEEDED


def test_run_watch_core_skips_if_already_running() -> None:
    watch = _watch()
    existing = PipelineRun(
        id=uuid.uuid4(),
        watch_id=watch.id,
        status=RunStatus.RUNNING,
        started_at=_NOW,
    )
    db = FakeSession(watch, existing)
    result = run_watch_core(db, watch, _deps())
    assert result["skipped"] == "already_running"


def test_run_watch_core_processes_items() -> None:
    records = [
        {"id": "1", "title": "Python dev", "body": "x" * 700},
        {"id": "2", "title": "Java dev", "body": "y" * 700},
    ]
    watch = _watch()
    db = FakeSession(watch)
    result = run_watch_core(db, watch, _deps(records))
    assert result["items"] == 2
