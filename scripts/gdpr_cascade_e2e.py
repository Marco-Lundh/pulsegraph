#!/usr/bin/env python
"""End-to-end GDPR cascade verification against real Postgres (ADR 0018).

The FakeSession unit tests cannot exercise foreign-key ON DELETE CASCADE,
so this script confirms against a live database that:

  1. **Erasure** — deleting a user removes all their owned data and the
     derived analysis/evaluation/notification provenance chain.
  2. **Retention purge** — ``purge_expired_data`` deletes items older than
     the window and cascades their provenance chain, while keeping fresh
     items.

    docker compose up -d        # or docker-compose; or let this run it
    uv run python scripts/gdpr_cascade_e2e.py
"""

import datetime
import pathlib
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pulsegraph.config import get_settings
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
from pulsegraph.worker.retention import purge_expired_data

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from smoke_e2e import _compose_cmd, _run  # noqa: E402


def _seed_user(db: Session, label: str) -> User:
    import uuid

    user = User(
        id=uuid.uuid4(),
        email=f"gdpr-{label}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        role=UserRole.USER,
    )
    db.add(user)
    db.flush()
    return user


def _seed_chain(
    db: Session, user: User, *, fetched_at: datetime.datetime
) -> dict:
    """Create watch + run + Item->Analysis->Evaluation->Notification."""
    import uuid

    watch = Watch(
        id=uuid.uuid4(),
        user_id=user.id,
        source=SourceKind.JOBTECH,
        prompt="python",
        config={},
        is_active=True,
        schedule_interval=datetime.timedelta(hours=1),
        next_run_at=fetched_at,
    )
    db.add(watch)
    db.flush()
    run = PipelineRun(
        id=uuid.uuid4(),
        watch_id=watch.id,
        status=RunStatus.SUCCEEDED,
        started_at=fetched_at,
    )
    db.add(run)
    db.flush()
    item = Item(
        id=uuid.uuid4(),
        user_id=user.id,
        watch_id=watch.id,
        run_id=run.id,
        source=SourceKind.JOBTECH,
        raw_payload={"title": "x"},
        content_hash=uuid.uuid4().hex,
        fetched_at=fetched_at,
    )
    db.add(item)
    db.flush()
    analysis = Analysis(
        id=uuid.uuid4(),
        item_id=item.id,
        model_used=ModelKind.OLLAMA,
        model_version="llama3.1:8b",
        result="summary",
        confidence=0.9,
    )
    db.add(analysis)
    db.flush()
    evaluation = Evaluation(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        relevance_score=0.8,
        confidence=0.9,
        status=EvalStatus.APPROVED,
    )
    db.add(evaluation)
    notification = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        analysis_id=analysis.id,
        channel=NotificationChannel.DASHBOARD,
        dedup_key=f"jobtech:{item.id}",
        status=NotificationStatus.SENT,
        delivered_at=fetched_at,
    )
    db.add(notification)
    db.flush()
    return {
        "watch": watch.id,
        "run": run.id,
        "item": item.id,
        "analysis": analysis.id,
        "evaluation": evaluation.id,
        "notification": notification.id,
    }


_MODELS = {
    "watch": Watch,
    "run": PipelineRun,
    "item": Item,
    "analysis": Analysis,
    "evaluation": Evaluation,
    "notification": Notification,
}


def _counts(db: Session, ids: dict) -> dict:
    """Return how many of each seeded row still exist, by id."""
    return {
        name: db.query(model).filter(model.id == ids[name]).count()
        for name, model in _MODELS.items()
    }


def verify_erasure(db: Session) -> None:
    user = _seed_user(db, "erase")
    ids = _seed_chain(db, user, fetched_at=datetime.datetime.now(datetime.UTC))
    db.commit()

    before = _counts(db, ids)
    assert all(v == 1 for v in before.values()), before

    db.delete(user)
    db.commit()

    after = _counts(db, ids)
    assert all(v == 0 for v in after.values()), after
    print(f"erasure: full chain cascaded on user delete -> {after}")


def verify_purge(db: Session) -> None:
    now = datetime.datetime.now(datetime.UTC)
    user = _seed_user(db, "purge")
    old = _seed_chain(db, user, fetched_at=now - datetime.timedelta(days=200))
    fresh = _seed_chain(db, user, fetched_at=now - datetime.timedelta(days=5))
    db.commit()

    result = purge_expired_data(db, now=now, retention_days=90)
    print(f"purge result: {result}")

    old_after = _counts(db, old)
    fresh_after = _counts(db, fresh)
    assert old_after["item"] == 0, old_after
    assert old_after["analysis"] == 0, old_after
    assert old_after["evaluation"] == 0, old_after
    assert old_after["notification"] == 0, old_after
    assert fresh_after["item"] == 1, fresh_after
    assert fresh_after["analysis"] == 1, fresh_after
    assert fresh_after["notification"] == 1, fresh_after
    print(f"purge: old chain removed, fresh kept -> fresh={fresh_after}")

    db.delete(user)
    db.commit()


def run_checks(*, manage_compose: bool = True) -> None:
    """Run both cascade checks, raising AssertionError on any failure."""
    settings = get_settings()
    if manage_compose:
        _run([*_compose_cmd(), "up", "-d", "--wait"])
    _run(["uv", "run", "alembic", "upgrade", "head"])

    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        verify_erasure(db)
        verify_purge(db)

    print("\nGDPR cascade E2E PASSED")


def main() -> int:
    import subprocess

    try:
        run_checks()
    except (AssertionError, subprocess.CalledProcessError) as exc:
        print(f"\nGDPR cascade E2E FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
