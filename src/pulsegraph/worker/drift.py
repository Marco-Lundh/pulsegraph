"""Automatic recovery of drift-paused sources (ADR 0010).

A source paused for schema drift used to be resumed only by an explicit
admin action. This re-probes each paused source on a schedule: if the
upstream schema is well-formed again, the pause is cleared automatically
so the scheduler starts triggering its watches. The probe is conservative
— the pause is only lifted when a fetched sample actually validates, so a
still-broken or unreachable source stays paused (the manual admin resume
remains the guaranteed path).
"""

import datetime

from sqlalchemy.orm import Session

from pulsegraph.db.models import AuditLogEntry, SourceHealth
from pulsegraph.domain.enums import SourceStatus
from pulsegraph.pipeline.contracts import UnknownSourceError
from pulsegraph.pipeline.local import DictSourceRegistry
from pulsegraph.sources.base import SourcePlugin
from pulsegraph.sources.errors import SchemaValidationError

# How many fetched records to validate before declaring the schema healthy.
_PROBE_SAMPLE = 5


def probe_source_schema(
    plugin: SourcePlugin, probe_query: str = ""
) -> str | None:
    """Re-probe a source's schema; return a drift detail, or None if healthy.

    Fetches a small sample and validates it. Any fetch error, empty result,
    or validation failure means the schema cannot be confirmed healthy, so a
    reason string is returned and the caller keeps the source paused.
    """
    try:
        records = plugin.fetch(probe_query)
    except Exception as exc:  # noqa: BLE001 - any fetch failure keeps it paused
        return f"probe fetch failed: {exc}"
    if not records:
        return "probe returned no records to validate"
    for record in records[:_PROBE_SAMPLE]:
        try:
            plugin.validate_schema(record)
        except SchemaValidationError as exc:
            return str(exc)
    return None


def recheck_paused_sources(
    db: Session,
    registry: DictSourceRegistry,
    *,
    now: datetime.datetime | None = None,
    probe_query: str = "",
) -> dict:
    """Re-probe every paused source and auto-resume the ones that healed.

    Adds rows/updates without a separate transaction of its own beyond the
    final commit. Filtered in Python too, so it is correct under the
    FakeSession test double (mirrors ``scheduler.select_due_watches``).
    """
    now = now or datetime.datetime.now(datetime.UTC)
    paused = [
        row
        for row in db.query(SourceHealth)
        .filter(SourceHealth.status == SourceStatus.PAUSED)
        .all()
        if row.status == SourceStatus.PAUSED
    ]

    cleared: list[str] = []
    for row in paused:
        try:
            plugin = registry.get(row.source)
        except UnknownSourceError:
            # No plugin registered for this source; leave it paused.
            continue
        drift = probe_source_schema(plugin, probe_query)
        row.last_checked_at = now
        if drift is not None:
            continue
        row.status = SourceStatus.HEALTHY
        row.drift_detail = None
        cleared.append(row.source.value)
        db.add(
            AuditLogEntry(
                actor_user_id=None,
                action="source.auto_resume",
                entity_type="source_health",
                entity_id=None,
                meta={"source": row.source.value},
            )
        )
    db.commit()
    return {"rechecked": len(paused), "cleared": cleared}


async def run_drift_recheck(ctx: dict) -> dict:
    """arq cron entry: auto-resume paused sources whose schema recovered."""
    db: Session = ctx["db_factory"]()
    try:
        deps = ctx["pipeline_deps"]
        return recheck_paused_sources(db, deps.registry)
    finally:
        db.close()
