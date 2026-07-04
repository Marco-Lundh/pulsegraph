"""Tests for the eval-health aggregate (ADR 0006)."""

import datetime
import uuid

from pulsegraph.api._fake import FakeSession
from pulsegraph.api.eval_health import eval_health_summary
from pulsegraph.db.models import Evaluation
from pulsegraph.domain.enums import EvalStatus

_NOW = datetime.datetime.now(datetime.UTC)


def _evaluation(
    status: EvalStatus, evaluated_at: datetime.datetime
) -> Evaluation:
    return Evaluation(
        id=uuid.uuid4(),
        analysis_id=uuid.uuid4(),
        relevance_score=0.5,
        confidence=0.8,
        status=status,
        evaluated_at=evaluated_at,
    )


def test_eval_health_empty_window_reports_no_data() -> None:
    db = FakeSession()
    result = eval_health_summary(db, _NOW)
    assert result["total"] == 0
    assert result["pct_approved"] is None


def test_eval_health_all_approved() -> None:
    db = FakeSession(
        _evaluation(EvalStatus.APPROVED, _NOW),
        _evaluation(EvalStatus.APPROVED, _NOW),
    )
    result = eval_health_summary(db, _NOW)
    assert result["total"] == 2
    assert result["approved"] == 2
    assert result["review"] == 0
    assert result["pct_approved"] == 1.0


def test_eval_health_mixed_verdicts() -> None:
    db = FakeSession(
        _evaluation(EvalStatus.APPROVED, _NOW),
        _evaluation(EvalStatus.APPROVED, _NOW),
        _evaluation(EvalStatus.APPROVED, _NOW),
        _evaluation(EvalStatus.REVIEW, _NOW),
    )
    result = eval_health_summary(db, _NOW)
    assert result["total"] == 4
    assert result["approved"] == 3
    assert result["review"] == 1
    assert result["pct_approved"] == 0.75


def test_eval_health_excludes_evaluations_outside_window() -> None:
    old = _evaluation(EvalStatus.APPROVED, _NOW - datetime.timedelta(hours=48))
    recent = _evaluation(
        EvalStatus.APPROVED, _NOW - datetime.timedelta(hours=1)
    )
    db = FakeSession(old, recent)
    result = eval_health_summary(db, _NOW, lookback_hours=24)
    assert result["total"] == 1
