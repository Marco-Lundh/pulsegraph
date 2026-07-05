"""Cost-ledger aggregation for the admin dashboard (ADR 0008).

``cost_events`` records one row per model call (tokens + USD). This
module rolls those rows up into a per-user spend view over a lookback
window so an operator can see who is driving cloud-model cost. Kept a
pure function (like ``eval_health_summary``) so it is unit-testable
without a live database, and separate from ``health.py`` (infra/ops)
because this is product/billing signal.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from pulsegraph.db.models import CostEvent, User


def cost_summary(
    db: Session,
    now: datetime.datetime,
    *,
    lookback_days: int = 30,
) -> dict:
    """Aggregate cloud-model spend per user over the lookback window.

    Returns overall totals plus a ``by_user`` breakdown (email, event
    count, tokens in/out, USD), sorted by spend descending. The window is
    applied in the query and again in Python so the result is correct
    under the FakeSession test double, whose ``filter`` is a no-op (same
    pattern as ``scheduler.select_due_watches`` and ``health.py``).
    """
    cutoff = now - datetime.timedelta(days=lookback_days)
    events = [
        e
        for e in db.query(CostEvent)
        .filter(CostEvent.created_at >= cutoff)
        .all()
        if e.created_at >= cutoff
    ]
    email_by_id = {u.id: u.email for u in db.query(User).all()}

    agg: dict[uuid.UUID, dict] = {}
    total_usd = 0.0
    total_in = 0
    total_out = 0
    for e in events:
        row = agg.setdefault(
            e.user_id,
            {"events": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0},
        )
        row["events"] += 1
        row["tokens_in"] += e.tokens_in
        row["tokens_out"] += e.tokens_out
        # cost_usd is a Numeric column (Decimal from real Postgres); coerce
        # to float so the sum and the JSON response are plain numbers.
        row["cost_usd"] += float(e.cost_usd)
        total_usd += float(e.cost_usd)
        total_in += e.tokens_in
        total_out += e.tokens_out

    by_user = [
        {
            "user_id": str(user_id),
            "email": email_by_id.get(user_id),
            "events": v["events"],
            "tokens_in": v["tokens_in"],
            "tokens_out": v["tokens_out"],
            "cost_usd": round(v["cost_usd"], 6),
        }
        for user_id, v in agg.items()
    ]
    by_user.sort(key=lambda r: r["cost_usd"], reverse=True)

    return {
        "window_days": lookback_days,
        "total_usd": round(total_usd, 6),
        "total_tokens_in": total_in,
        "total_tokens_out": total_out,
        "by_user": by_user,
    }
