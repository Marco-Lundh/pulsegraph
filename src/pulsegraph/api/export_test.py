"""Tests for the GDPR data-portability export (ADR 0018)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession, make_client
from pulsegraph.api.export import export_user_data
from pulsegraph.db.models import (
    Analysis,
    AuditLogEntry,
    CostEvent,
    Evaluation,
    Item,
    Notification,
    NotificationSetting,
    User,
    Watch,
)
from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
    SourceKind,
    UserRole,
)

_NOW = datetime.datetime(2026, 6, 28, tzinfo=datetime.UTC)


def _user(email: str = "alice@example.com") -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="x",
        role=UserRole.USER,
        created_at=_NOW,
    )


def _seed(user: User) -> FakeSession:
    watch = Watch(
        id=uuid.uuid4(),
        user_id=user.id,
        source=SourceKind.JOBTECH,
        prompt="python",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
    )
    item = Item(
        id=uuid.uuid4(),
        user_id=user.id,
        watch_id=watch.id,
        source=SourceKind.JOBTECH,
        raw_payload={"title": "Dev"},
        content_hash="h1",
        embedding=[0.0] * 768,
        fetched_at=_NOW,
    )
    analysis = Analysis(
        id=uuid.uuid4(),
        item_id=item.id,
        model_used=ModelKind.OLLAMA,
        model_version="llama3.1:8b",
        result="summary",
        confidence=0.9,
    )
    evaluation = Evaluation(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        relevance_score=0.8,
        confidence=0.9,
        status=EvalStatus.APPROVED,
    )
    notif = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        analysis_id=analysis.id,
        channel=NotificationChannel.DASHBOARD,
        dedup_key="jobtech:1",
        status=NotificationStatus.SENT,
        delivered_at=_NOW,
    )
    setting = NotificationSetting(
        user_id=user.id,
        channel=NotificationChannel.EMAIL,
        frequency=NotificationFrequency.INSTANT,
        destination="alice@example.com",
        is_active=True,
    )
    cost = CostEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        model=ModelKind.CLAUDE,
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.01,
        created_at=_NOW,
    )
    return FakeSession(
        user, watch, item, analysis, evaluation, notif, setting, cost
    )


def test_export_includes_all_user_owned_data() -> None:
    user = _user()
    data = export_user_data(_seed(user), user)

    assert data["profile"]["email"] == "alice@example.com"
    assert len(data["watches"]) == 1
    assert len(data["items"]) == 1
    assert "embedding" not in data["items"][0]
    assert len(data["analyses"]) == 1
    assert len(data["evaluations"]) == 1
    assert len(data["notifications"]) == 1
    assert len(data["notification_settings"]) == 1
    assert len(data["cost_events"]) == 1
    assert data["cost_events"][0]["cost_usd"] == 0.01


def test_export_excludes_other_users_data() -> None:
    user = _user()
    db = _seed(user)
    db.add(
        Item(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            watch_id=uuid.uuid4(),
            source=SourceKind.JOBTECH,
            raw_payload={},
            content_hash="other",
            fetched_at=_NOW,
        )
    )

    data = export_user_data(db, user)

    assert len(data["items"]) == 1
    assert data["items"][0]["content_hash"] == "h1"


def test_export_endpoint_returns_data_and_audits() -> None:
    user = _user()
    db = _seed(user)
    client, _, _ = make_client(db=db, user=user)

    resp = client.get("/auth/me/export")

    assert resp.status_code == 200
    body = resp.json()
    assert body["profile"]["email"] == user.email
    assert len(body["watches"]) == 1
    assert len(body["analyses"]) == 1
    audits = db.query(AuditLogEntry).all()
    assert any(a.action == "user.export" for a in audits)
