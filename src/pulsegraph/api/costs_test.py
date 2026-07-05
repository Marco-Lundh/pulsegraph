"""Tests for the cost-ledger aggregation (ADR 0008)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.api.costs import cost_summary
from pulsegraph.db.models import CostEvent, User
from pulsegraph.domain.enums import ModelKind, UserRole

_NOW = datetime.datetime.now(datetime.UTC)


def _user(email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        password_hash="",
        role=UserRole.USER,
    )


def _event(
    user_id: uuid.UUID,
    *,
    cost_usd: float,
    tokens_in: int = 100,
    tokens_out: int = 50,
    created_at: datetime.datetime | None = None,
    model: ModelKind = ModelKind.CLAUDE,
) -> CostEvent:
    return CostEvent(
        id=uuid.uuid4(),
        user_id=user_id,
        run_id=uuid.uuid4(),
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        created_at=created_at or _NOW,
    )


def test_cost_summary_empty() -> None:
    db = FakeSession()
    summary = cost_summary(db, _NOW)
    assert summary["total_usd"] == 0.0
    assert summary["by_user"] == []


def test_cost_summary_aggregates_per_user_sorted_by_spend() -> None:
    big = _user("big@example.com")
    small = _user("small@example.com")
    db = FakeSession(
        big,
        small,
        _event(big.id, cost_usd=0.4, tokens_in=1000, tokens_out=200),
        _event(big.id, cost_usd=0.1, tokens_in=200, tokens_out=100),
        _event(small.id, cost_usd=0.05, tokens_in=50, tokens_out=25),
    )

    summary = cost_summary(db, _NOW)

    assert summary["total_usd"] == 0.55
    assert summary["total_tokens_in"] == 1250
    assert summary["total_tokens_out"] == 325
    # Sorted by spend descending: big first.
    assert [r["email"] for r in summary["by_user"]] == [
        "big@example.com",
        "small@example.com",
    ]
    big_row = summary["by_user"][0]
    assert big_row["events"] == 2
    assert big_row["cost_usd"] == 0.5
    assert big_row["tokens_in"] == 1200


def test_cost_summary_excludes_events_outside_window() -> None:
    u = _user("u@example.com")
    old = _event(
        u.id,
        cost_usd=9.9,
        created_at=_NOW - datetime.timedelta(days=60),
    )
    recent = _event(
        u.id,
        cost_usd=0.2,
        created_at=_NOW - datetime.timedelta(days=1),
    )
    db = FakeSession(u, old, recent)

    summary = cost_summary(db, _NOW, lookback_days=30)

    assert summary["total_usd"] == 0.2
    assert summary["by_user"][0]["events"] == 1
