"""Tests for /admin endpoints (role guard + review queue)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, _make_user, make_client
from pulsegraph.db.models import (
    AuditLogEntry,
    CostEvent,
    Evaluation,
    Prompt,
    ReviewDecision,
    SourceHealth,
    User,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    PromptRole,
    SourceKind,
    SourceStatus,
    UserRole,
)
from pulsegraph.domain.enums import ReviewDecision as ReviewDecisionEnum

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


def test_admin_resume_source_clears_drift() -> None:
    # Resuming a drift-paused source flips it back to healthy so the
    # scheduler starts triggering it again (ADR 0010).
    admin = _make_user(UserRole.ADMIN)
    paused = SourceHealth(
        source=SourceKind.JOBTECH,
        status=SourceStatus.PAUSED,
        drift_detail="missing field",
        last_checked_at=_NOW,
    )
    db = FakeSession(admin, paused)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post("/admin/source-health/jobtech/resume")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["drift_detail"] is None
    assert paused.status == SourceStatus.HEALTHY
    # The action is audit-logged (ADR 0021).
    actions = [e.action for e in db.query(AuditLogEntry).all()]
    assert "source.resume" in actions


def test_admin_resume_unknown_source_404() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.post("/admin/source-health/riksdagen/resume")
    assert resp.status_code == 404


def test_non_admin_cannot_resume_source() -> None:
    client, _, _ = make_client()
    resp = client.post("/admin/source-health/jobtech/resume")
    assert resp.status_code == 403


# --- eval health ---


def test_admin_eval_health_reports_pct_approved() -> None:
    admin = _make_user(UserRole.ADMIN)
    approved = _evaluation(EvalStatus.APPROVED)
    db = FakeSession(admin, approved)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.get("/admin/eval-health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["pct_approved"] == 1.0


def test_non_admin_cannot_access_eval_health() -> None:
    client, _, _ = make_client()
    resp = client.get("/admin/eval-health")
    assert resp.status_code == 403


# --- prompt registry (ADR 0011) ---


def _prompt(
    name: str = "analyzer",
    version: int = 1,
    *,
    is_active: bool = True,
    template: str = "v1 instruction",
    role: PromptRole = PromptRole.ANALYZER,
) -> Prompt:
    return Prompt(
        id=uuid.uuid4(),
        name=name,
        role=role,
        version=version,
        template=template,
        is_active=is_active,
        created_at=_NOW,
    )


def test_admin_can_list_prompts() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(
        admin, _prompt(version=1, is_active=False), _prompt(version=2)
    )
    client, _, _ = make_client(db=db, user=admin)

    resp = client.get("/admin/prompts")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # Newest version first within a name.
    assert body[0]["version"] == 2


def test_non_admin_cannot_access_prompts() -> None:
    client, _, _ = make_client()
    assert client.get("/admin/prompts").status_code == 403


def test_admin_create_prompt_adds_active_version() -> None:
    admin = _make_user(UserRole.ADMIN)
    current = _prompt(version=1, is_active=True, template="old")
    db = FakeSession(admin, current)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post(
        "/admin/prompts",
        json={"name": "analyzer", "template": "new instruction"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 2
    assert body["is_active"] is True
    assert body["role"] == "analyzer"  # inherited from the existing name
    # The previously active version is deactivated.
    assert current.is_active is False
    # The action is audit-logged.
    actions = [e.action for e in db.query(AuditLogEntry).all()]
    assert "prompt.create" in actions


def test_admin_create_prompt_draft_without_activating() -> None:
    admin = _make_user(UserRole.ADMIN)
    current = _prompt(version=1, is_active=True)
    db = FakeSession(admin, current)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post(
        "/admin/prompts",
        json={"name": "analyzer", "template": "draft", "activate": False},
    )

    assert resp.status_code == 201
    assert resp.json()["is_active"] is False
    # The active version is untouched.
    assert current.is_active is True


def test_create_prompt_rejects_blank_template() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin, _prompt(version=1))
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post(
        "/admin/prompts",
        json={"name": "analyzer", "template": "   "},
    )

    assert resp.status_code == 422


def test_create_prompt_unknown_name_returns_400() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post(
        "/admin/prompts",
        json={"name": "does-not-exist", "template": "x"},
    )

    assert resp.status_code == 400


def test_admin_activate_prompt_switches_active_version() -> None:
    admin = _make_user(UserRole.ADMIN)
    v1 = _prompt(version=1, is_active=True)
    v2 = _prompt(version=2, is_active=False)
    db = FakeSession(admin, v1, v2)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.post(f"/admin/prompts/{v2.id}/activate")

    assert resp.status_code == 200
    assert v2.is_active is True
    assert v1.is_active is False


def test_activate_unknown_prompt_returns_404() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.post(f"/admin/prompts/{uuid.uuid4()}/activate")
    assert resp.status_code == 404


# --- cost ledger ---


def test_admin_costs_reports_per_user_spend() -> None:
    admin = _make_user(UserRole.ADMIN)
    spend_user = _make_user(UserRole.USER)
    event = CostEvent(
        id=uuid.uuid4(),
        user_id=spend_user.id,
        run_id=uuid.uuid4(),
        model=ModelKind.CLAUDE,
        tokens_in=1000,
        tokens_out=200,
        cost_usd=0.42,
        created_at=_NOW,
    )
    db = FakeSession(admin, spend_user, event)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.get("/admin/costs")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_usd"] == 0.42
    assert body["by_user"][0]["email"] == spend_user.email
    assert body["by_user"][0]["cost_usd"] == 0.42


def test_non_admin_cannot_access_costs() -> None:
    client, _, _ = make_client()
    resp = client.get("/admin/costs")
    assert resp.status_code == 403


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


def test_review_queue_excludes_already_decided_evaluations() -> None:
    admin = _make_user(UserRole.ADMIN)
    ev = _evaluation(EvalStatus.REVIEW)
    decision = ReviewDecision(
        id=uuid.uuid4(),
        evaluation_id=ev.id,
        reviewer_id=admin.id,
        decision=ReviewDecisionEnum.APPROVED,
        decided_at=_NOW,
    )
    db = FakeSession(admin, ev, decision)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.get("/admin/review-queue")

    assert resp.status_code == 200
    assert resp.json() == []


def test_admin_decide_unknown_evaluation_returns_404() -> None:
    admin = _make_user(UserRole.ADMIN)
    db = FakeSession(admin)
    client, _, _ = make_client(db=db, user=admin)
    resp = client.post(
        f"/admin/review-queue/{uuid.uuid4()}/decide",
        json={"decision": "approved"},
    )
    assert resp.status_code == 404


# --- list users ---


def test_admin_can_list_users() -> None:
    admin = _make_user(UserRole.ADMIN)
    other = _make_user(UserRole.USER)
    admin.created_at = _NOW
    other.created_at = _NOW
    db = FakeSession(admin, other)
    client, _, _ = make_client(db=db, user=admin)

    resp = client.get("/admin/users")

    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert emails == {admin.email, other.email}


def test_non_admin_cannot_list_users() -> None:
    client, _, _ = make_client()
    resp = client.get("/admin/users")
    assert resp.status_code == 403


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
