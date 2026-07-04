"""Tests for GET /runs."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.db.models import PipelineRun, User, Watch
from pulsegraph.domain.enums import RunStatus, SourceKind, UserRole

_NOW = datetime.datetime.now(datetime.UTC)


def _watch(user_id: uuid.UUID) -> Watch:
    return Watch(
        id=uuid.uuid4(),
        user_id=user_id,
        source=SourceKind.JOBTECH,
        prompt="python jobs",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _run(watch_id: uuid.UUID, started_at: datetime.datetime) -> PipelineRun:
    return PipelineRun(
        id=uuid.uuid4(),
        watch_id=watch_id,
        status=RunStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=started_at + datetime.timedelta(seconds=5),
    )


def test_list_runs_empty() -> None:
    client, _, _ = make_client()
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_excludes_other_users_runs() -> None:
    owner = User(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    other = User(
        id=uuid.uuid4(),
        email="other@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    owner_watch = _watch(owner.id)
    other_watch = _watch(other.id)
    db = FakeSession(
        owner,
        other,
        owner_watch,
        other_watch,
        _run(owner_watch.id, _NOW),
        _run(other_watch.id, _NOW),
    )
    client, _, _ = make_client(db=db, user=owner)

    resp = client.get("/runs")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["watch_id"] == str(owner_watch.id)


def test_list_runs_filters_by_watch_id() -> None:
    user = User(
        id=uuid.uuid4(),
        email="u@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch_a = _watch(user.id)
    watch_b = _watch(user.id)
    db = FakeSession(
        user,
        watch_a,
        watch_b,
        _run(watch_a.id, _NOW),
        _run(watch_b.id, _NOW),
    )
    client, _, _ = make_client(db=db, user=user)

    resp = client.get(f"/runs?watch_id={watch_a.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["watch_id"] == str(watch_a.id)


def test_list_runs_filters_by_since() -> None:
    user = User(
        id=uuid.uuid4(),
        email="u2@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    old_run = _run(watch.id, _NOW - datetime.timedelta(days=30))
    recent_run = _run(watch.id, _NOW - datetime.timedelta(days=1))
    db = FakeSession(user, watch, old_run, recent_run)
    client, _, _ = make_client(db=db, user=user)

    since = _NOW - datetime.timedelta(days=7)
    resp = client.get("/runs", params={"since": since.isoformat()})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(recent_run.id)
