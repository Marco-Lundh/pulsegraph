"""Tests for /admin endpoints (role guard + review queue)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, _make_user, make_client
from pulsegraph.db.models import (
    AuditLogEntry,
    Evaluation,
    SourceHealth,
    User,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    SourceKind,
    SourceStatus,
    UserRole,
)

_NOW = datetime.datetime.now(datetime.UTC)


def _evaluation(status: EvalStatus = EvalStatus.REVIEW) -> Evaluation:
    return Evaluation(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        relevance_score=0.5,
        confidence=0.8,
        status=status,
        evaluated_at=_NOW,
    )


def _source_health() -> SourceHealth:
    return SourceHealth(
        source=SourceKind.JOBTECH,
        status=SourceStatus.HEALTHY,
        drift_detail=None,
        last_checked_at=_NOW,
    )


# --- role guard ---


def test_non_admin_cannot_access_admin_routes() -> None:
    client, user, _ = make_client()
    assert user.role == UserRole.USER
    resp = client.get("/admin/source-health")
    assert resp.status_code == 403


def _patch_ops(monkeypatch, *, spend=8.5, depth=0, worker=True) -> None:
    from pulsegraph.api import health

    # Stub the Redis-backed probes (called inside operational_summary) so
    # the endpoint needs no live Redis.
    monkeypatch.setattr(health, "get_monthly_cost", lambda _r: spend)
    monkeypatch.setattr(health, "queue_depth", lambda _r: depth)
    monkeypatch.setattr(health, "worker_alive", lambda _r: worker)


def test_admin_ops_reports_spend_vs_cap(monkeypatch) -> None:
    # Default cap is 10.0 with a 0.8 alert ratio, so 8.5 is near the cap.
    _patch_ops(monkeypatch, spend=8.5)
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.get("/admin/ops")

    assert resp.status_code == 200
    spend = resp.json()["spend"]
    assert spend["spend_usd"] == 8.5
    assert spend["near_cap"] is True
    assert spend["over_cap"] is False


def test_admin_ops_reports_queue_and_worker(monkeypatch) -> None:
    _patch_ops(monkeypatch, depth=5, worker=True)
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)

    queue = client.get("/admin/ops").json()["queue"]

    assert queue["depth"] == 5
    assert queue["worker_alive"] is True
    assert queue["worker_down"] is False
    assert queue["backlog"] is False


def test_admin_ops_flags_paused_sources(monkeypatch) -> None:
    _patch_ops(monkeypatch)
    admin = _make_user(UserRole.ADMIN)
    paused = SourceHealth(
        source=SourceKind.JOBTECH, status=SourceStatus.PAUSED
    )
    db = FakeSession(admin, paused)
    client, _, _ = make_client(db=db, user=admin)

    sources = client.get("/admin/ops").json()["sources"]

    assert sources["paused"] == ["jobtech"]
    assert sources["alert"] is True


def test_admin_can_access_source_health() -> None:
    admin = _make_user(UserRole.ADMIN)
    sh = _source_health()
    db = FakeSession(admin, sh)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.get("/admin/source-health")
    assert resp.status_code == 200
    assert resp.json()[0]["source"] == "jobtech"


# --- review queue ---


def test_admin_list_review_queue() -> None:
    admin = _make_user(UserRole.ADMIN)
    ev = _evaluation(EvalStatus.REVIEW)
    db = FakeSession(admin, ev)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.get("/admin/review-queue")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_admin_decide_records_decision() -> None:
    admin = _make_user(UserRole.ADMIN)
    ev = _evaluation(EvalStatus.REVIEW)
    db = FakeSession(admin, ev)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.post(
        f"/admin/review-queue/{ev.id}/decide",
        json={"decision": "approved"},
    )
    assert resp.status_code == 201
    assert resp.json()["decision"] == "approved"


def test_admin_decide_unknown_evaluation_returns_404() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.post(
        f"/admin/review-queue/{uuid.uuid4()}/decide",
        json={"decision": "approved"},
    )
    assert resp.status_code == 404


# --- delete user (GDPR erasure) ---


def test_admin_delete_user_erases_and_audits() -> None:
    admin = _make_user(UserRole.ADMIN)
    target = _make_user(UserRole.USER)
    db = FakeSession(admin, target)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.delete(f"/admin/users/{target.id}")

    assert resp.status_code == 204
    assert target not in db.query(User).all()
    audits = db.query(AuditLogEntry).all()
    assert audits[-1].action == "user.delete"
    assert audits[-1].entity_id == target.id
    assert audits[-1].meta["by"] == "admin"


def test_admin_delete_unknown_user_returns_404() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.delete(f"/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_non_admin_cannot_delete_user() -> None:
    client, _, _ = make_client()
    resp = client.delete(f"/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 403
