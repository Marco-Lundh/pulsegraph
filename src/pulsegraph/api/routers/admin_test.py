"""Tests for /admin endpoints (role guard + review queue)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, _make_user, make_client
from pulsegraph.db.models import Evaluation, SourceHealth
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
