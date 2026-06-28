"""Assemble a user's personal data for GDPR portability export (ADR 0018).

A read-only aggregation of every record keyed to one user, shaped into a
plain JSON-serializable dict. Each table is filtered both in the query
and again in Python, so the result is correct under the FakeSession test
double, whose ``filter`` is a no-op (mirrors :mod:`worker.scheduler`).
"""

import datetime
import uuid
from typing import Any

from sqlalchemy.orm import Session

from pulsegraph.db.models import (
    Analysis,
    CostEvent,
    Evaluation,
    Item,
    Notification,
    NotificationSetting,
    User,
    Watch,
)


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _owned(db: Session, model: type, user_id: uuid.UUID) -> list:
    """Return the user's rows for a model that has a ``user_id`` column."""
    return [
        row
        for row in db.query(model).filter(model.user_id == user_id).all()
        if row.user_id == user_id
    ]


def _watch(w: Watch) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "source": w.source,
        "prompt": w.prompt,
        "config": w.config,
        "is_active": w.is_active,
        "schedule_interval_seconds": w.schedule_interval.total_seconds(),
        "last_run_at": _iso(w.last_run_at),
        "next_run_at": _iso(w.next_run_at),
        "created_at": _iso(w.created_at),
    }


def _item(i: Item) -> dict[str, Any]:
    # The 768-dim embedding is an internal vector, not portable user data.
    return {
        "id": str(i.id),
        "watch_id": str(i.watch_id),
        "source": i.source,
        "external_id": i.external_id,
        "raw_payload": i.raw_payload,
        "content_hash": i.content_hash,
        "fetched_at": _iso(i.fetched_at),
    }


def _analysis(a: Analysis) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "item_id": str(a.item_id),
        "model_used": a.model_used,
        "model_version": a.model_version,
        "result": a.result,
        "confidence": a.confidence,
        "created_at": _iso(a.created_at),
    }


def _evaluation(e: Evaluation) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "analysis_id": str(e.analysis_id),
        "relevance_score": e.relevance_score,
        "confidence": e.confidence,
        "status": e.status,
        "evaluated_at": _iso(e.evaluated_at),
    }


def _notification(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "analysis_id": str(n.analysis_id),
        "channel": n.channel,
        "dedup_key": n.dedup_key,
        "status": n.status,
        "delivered_at": _iso(n.delivered_at),
    }


def _setting(s: NotificationSetting) -> dict[str, Any]:
    return {
        "channel": s.channel,
        "frequency": s.frequency,
        "destination": s.destination,
        "is_active": s.is_active,
    }


def _cost_event(c: CostEvent) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "model": c.model,
        "tokens_in": c.tokens_in,
        "tokens_out": c.tokens_out,
        "cost_usd": float(c.cost_usd),
        "created_at": _iso(c.created_at),
    }


def export_user_data(db: Session, user: User) -> dict[str, Any]:
    """Collect every record we hold that is keyed to *user* (ADR 0018).

    Derived rows (analyses, evaluations) have no ``user_id`` of their own,
    so they are reached through the user's items.
    """
    items = _owned(db, Item, user.id)
    item_ids = {i.id for i in items}
    analyses = [a for a in db.query(Analysis).all() if a.item_id in item_ids]
    analysis_ids = {a.id for a in analyses}
    evaluations = [
        e for e in db.query(Evaluation).all() if e.analysis_id in analysis_ids
    ]
    return {
        "profile": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
            "created_at": _iso(user.created_at),
        },
        "watches": [_watch(w) for w in _owned(db, Watch, user.id)],
        "items": [_item(i) for i in items],
        "analyses": [_analysis(a) for a in analyses],
        "evaluations": [_evaluation(e) for e in evaluations],
        "notifications": [
            _notification(n) for n in _owned(db, Notification, user.id)
        ],
        "notification_settings": [
            _setting(s) for s in _owned(db, NotificationSetting, user.id)
        ],
        "cost_events": [
            _cost_event(c) for c in _owned(db, CostEvent, user.id)
        ],
    }
