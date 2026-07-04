"""Aggregate eval-quality signal for the dashboard (ADR 0006).

Kept in its own module deliberately: ``health.py`` keeps infrastructure
liveness distinct from this product-quality metric (see its docstring).
"""

import datetime
from typing import Any

from pulsegraph.db.models import Evaluation
from pulsegraph.domain.enums import EvalStatus


def eval_health_summary(
    db: Any, now: datetime.datetime, lookback_hours: int = 24
) -> dict:
    """Summarize Evaluator verdicts within the lookback window.

    ``pct_approved`` is ``None`` when there's nothing to report, so the
    caller can distinguish "no data" from "0% approved".
    """
    cutoff = now - datetime.timedelta(hours=lookback_hours)
    rows = db.query(Evaluation).filter(Evaluation.evaluated_at >= cutoff).all()
    # Filtered in Python too, so it is correct under the FakeSession test
    # double whose filter is a no-op.
    rows = [r for r in rows if r.evaluated_at >= cutoff]
    total = len(rows)
    approved = sum(1 for r in rows if r.status == EvalStatus.APPROVED)
    review = sum(1 for r in rows if r.status == EvalStatus.REVIEW)
    return {
        "window_hours": lookback_hours,
        "total": total,
        "approved": approved,
        "review": review,
        "pct_approved": round(approved / total, 4) if total else None,
    }
