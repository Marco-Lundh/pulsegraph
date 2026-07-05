"""Tests for GET /runs and GET /runs/{run_id}/items."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.db.models import (
    Analysis,
    Evaluation,
    Item,
    Notification,
    PipelineRun,
    User,
    Watch,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationStatus,
    RunStatus,
    SourceKind,
    UserRole,
)

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


def _run(
    watch_id: uuid.UUID,
    started_at: datetime.datetime,
    *,
    trace_id: str | None = None,
) -> PipelineRun:
    return PipelineRun(
        id=uuid.uuid4(),
        watch_id=watch_id,
        status=RunStatus.SUCCEEDED,
        langsmith_trace_id=trace_id,
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


def test_list_runs_exposes_langsmith_trace_id() -> None:
    # ADR 0007: the trace id is surfaced so the dashboard can link a run
    # back to its LangSmith execution trace.
    user = User(
        id=uuid.uuid4(),
        email="trace@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch.id, _NOW, trace_id="trace-abc-123")
    db = FakeSession(user, watch, run)
    client, _, _ = make_client(db=db, user=user)

    body = client.get("/runs").json()

    assert body[0]["langsmith_trace_id"] == "trace-abc-123"


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/items  (per-item model + eval, ADR 0002/0006)
# ---------------------------------------------------------------------------


def _chain(
    user_id: uuid.UUID,
    watch_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    model: ModelKind = ModelKind.CLAUDE,
    status: EvalStatus = EvalStatus.APPROVED,
    notified: bool = True,
) -> list:
    """Build a persisted item -> analysis -> evaluation (+notif) chain."""
    item = Item(
        id=uuid.uuid4(),
        user_id=user_id,
        watch_id=watch_id,
        run_id=run_id,
        source=SourceKind.JOBTECH,
        external_id="job-1",
        raw_payload={},
        content_hash="hash-1",
        fetched_at=_NOW,
    )
    analysis = Analysis(
        id=uuid.uuid4(),
        item_id=item.id,
        model_used=model,
        model_version="claude-3-5-sonnet"
        if model is ModelKind.CLAUDE
        else "llama3",
        params={},
        result="A relevant Python job at ACME.",
        confidence=0.91,
        created_at=_NOW,
    )
    evaluation = Evaluation(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        relevance_score=0.87,
        confidence=0.91,
        status=status,
        evaluated_at=_NOW,
    )
    rows = [item, analysis, evaluation]
    if notified:
        rows.append(
            Notification(
                id=uuid.uuid4(),
                user_id=user_id,
                analysis_id=analysis.id,
                channel=NotificationChannel.DASHBOARD,
                dedup_key="dedup-1",
                status=NotificationStatus.SENT,
                delivered_at=_NOW,
            )
        )
    return rows


def test_get_run_returns_run_with_trace() -> None:
    user = User(
        id=uuid.uuid4(),
        email="one@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch.id, _NOW, trace_id="trace-xyz")
    db = FakeSession(user, watch, run)
    client, _, _ = make_client(db=db, user=user)

    resp = client.get(f"/runs/{run.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(run.id)
    assert body["langsmith_trace_id"] == "trace-xyz"


def test_get_run_404_for_other_users_run() -> None:
    owner = User(
        id=uuid.uuid4(),
        email="o3@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    other = User(
        id=uuid.uuid4(),
        email="x3@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    other_watch = _watch(other.id)
    other_run = _run(other_watch.id, _NOW)
    db = FakeSession(owner, other, other_watch, other_run)
    client, _, _ = make_client(db=db, user=owner)

    resp = client.get(f"/runs/{other_run.id}")

    assert resp.status_code == 404


def test_run_items_returns_model_and_eval() -> None:
    user = User(
        id=uuid.uuid4(),
        email="items@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch.id, _NOW)
    chain = _chain(user.id, watch.id, run.id, model=ModelKind.CLAUDE)
    db = FakeSession(user, watch, run, *chain)
    client, _, _ = make_client(db=db, user=user)

    resp = client.get(f"/runs/{run.id}/items")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    assert row["model_used"] == "claude"
    assert row["model_version"] == "claude-3-5-sonnet"
    assert row["summary"] == "A relevant Python job at ACME."
    assert row["relevance_score"] == 0.87
    assert row["eval_status"] == "approved"
    assert row["notified"] is True
    assert row["external_id"] == "job-1"


def test_run_items_notified_false_without_notification() -> None:
    user = User(
        id=uuid.uuid4(),
        email="items2@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch.id, _NOW)
    chain = _chain(
        user.id,
        watch.id,
        run.id,
        model=ModelKind.OLLAMA,
        status=EvalStatus.REVIEW,
        notified=False,
    )
    db = FakeSession(user, watch, run, *chain)
    client, _, _ = make_client(db=db, user=user)

    row = client.get(f"/runs/{run.id}/items").json()[0]

    assert row["model_used"] == "ollama"
    assert row["eval_status"] == "review"
    assert row["notified"] is False


def test_run_items_404_for_other_users_run() -> None:
    owner = User(
        id=uuid.uuid4(),
        email="owner2@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    other = User(
        id=uuid.uuid4(),
        email="other2@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    other_watch = _watch(other.id)
    other_run = _run(other_watch.id, _NOW)
    db = FakeSession(owner, other, other_watch, other_run)
    client, _, _ = make_client(db=db, user=owner)

    resp = client.get(f"/runs/{other_run.id}/items")

    assert resp.status_code == 404


def test_run_items_empty_for_run_with_no_items() -> None:
    user = User(
        id=uuid.uuid4(),
        email="empty@example.com",
        password_hash="",
        role=UserRole.USER,
    )
    watch = _watch(user.id)
    run = _run(watch.id, _NOW)
    db = FakeSession(user, watch, run)
    client, _, _ = make_client(db=db, user=user)

    resp = client.get(f"/runs/{run.id}/items")

    assert resp.status_code == 200
    assert resp.json() == []
