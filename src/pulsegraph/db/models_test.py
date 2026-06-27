"""Tests for the ORM schema definition (no database required)."""

from pulsegraph.db import models
from pulsegraph.db.base import Base

EXPECTED_TABLES = {
    "users",
    "watches",
    "source_health",
    "pipeline_runs",
    "prompts",
    "items",
    "analyses",
    "evaluations",
    "review_decisions",
    "notifications",
    "notification_settings",
    "cost_events",
    "audit_log",
}


# --- table coverage ---


def test_all_documented_tables_are_mapped() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


# --- key constraints ---


def test_item_dedup_is_per_user() -> None:
    item = Base.metadata.tables["items"]
    unique_columns = {
        tuple(sorted(c.name for c in con.columns))
        for con in item.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }

    assert ("content_hash", "user_id") in unique_columns


def test_one_active_run_per_watch_index_exists() -> None:
    runs = Base.metadata.tables["pipeline_runs"]
    index = next(i for i in runs.indexes if i.name == "idx_runs_one_active")

    assert index.unique is True


def test_audit_metadata_column_is_named_metadata() -> None:
    # The attribute is `meta` but the column must be `metadata`.
    audit = Base.metadata.tables["audit_log"]

    assert "metadata" in audit.columns
    assert models.AuditLogEntry.meta is not None
