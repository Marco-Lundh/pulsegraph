"""Tests for automatic drift recovery (ADR 0010)."""

import datetime

from pulsegraph.api._fake import FakeSession
from pulsegraph.db.models import AuditLogEntry, SourceHealth
from pulsegraph.domain.enums import SourceKind, SourceStatus
from pulsegraph.pipeline.local import DictSourceRegistry, StaticSourcePlugin
from pulsegraph.sources.base import FetchedItem, SourcePlugin
from pulsegraph.worker.drift import (
    probe_source_schema,
    recheck_paused_sources,
)

_NOW = datetime.datetime.now(datetime.UTC)
_VALID = {"id": "1", "title": "Python dev", "body": "a great role"}
_DRIFTED = {"id": "1"}  # missing title/body


def _paused(source: SourceKind = SourceKind.JOBTECH) -> SourceHealth:
    return SourceHealth(
        source=source,
        status=SourceStatus.PAUSED,
        drift_detail="missing field: title",
        last_checked_at=_NOW - datetime.timedelta(hours=2),
    )


def _registry(records: list[dict]) -> DictSourceRegistry:
    reg = DictSourceRegistry()
    reg.register(StaticSourcePlugin(SourceKind.JOBTECH, records))
    return reg


class _ExplodingPlugin(SourcePlugin):
    kind = SourceKind.JOBTECH

    def fetch(self, query: str) -> list[dict]:
        raise RuntimeError("source unreachable")

    def validate_schema(self, record: dict) -> None:  # pragma: no cover
        pass

    def parse(self, record: dict) -> FetchedItem:  # pragma: no cover
        raise NotImplementedError


# --- probe_source_schema ---


def test_probe_returns_none_when_schema_valid() -> None:
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [_VALID])
    assert probe_source_schema(plugin) is None


def test_probe_returns_detail_when_still_drifted() -> None:
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [_DRIFTED])
    detail = probe_source_schema(plugin)
    assert detail is not None


def test_probe_returns_detail_when_no_records() -> None:
    plugin = StaticSourcePlugin(SourceKind.JOBTECH, [])
    assert (
        probe_source_schema(plugin) == "probe returned no records to validate"
    )


def test_probe_returns_detail_when_fetch_raises() -> None:
    detail = probe_source_schema(_ExplodingPlugin())
    assert detail is not None
    assert "probe fetch failed" in detail


# --- recheck_paused_sources ---


def test_recheck_clears_pause_when_schema_recovered() -> None:
    row = _paused()
    db = FakeSession(row)

    result = recheck_paused_sources(db, _registry([_VALID]), now=_NOW)

    assert row.status == SourceStatus.HEALTHY
    assert row.drift_detail is None
    assert row.last_checked_at == _NOW
    assert result["cleared"] == ["jobtech"]
    # The auto-resume is audit-logged (system actor).
    audits = db.query(AuditLogEntry).all()
    assert audits[-1].action == "source.auto_resume"


def test_recheck_keeps_pause_when_still_drifted() -> None:
    row = _paused()
    db = FakeSession(row)

    result = recheck_paused_sources(db, _registry([_DRIFTED]), now=_NOW)

    assert row.status == SourceStatus.PAUSED
    assert result["cleared"] == []
    # last_checked_at still advances so operators can see it was re-probed.
    assert row.last_checked_at == _NOW


def test_recheck_keeps_pause_when_no_plugin_registered() -> None:
    row = _paused()
    db = FakeSession(row)

    result = recheck_paused_sources(db, DictSourceRegistry(), now=_NOW)

    assert row.status == SourceStatus.PAUSED
    assert result["rechecked"] == 1
    assert result["cleared"] == []
