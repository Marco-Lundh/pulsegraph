"""Operational health checks and spend signal (ADR 0020).

Infrastructure liveness — database, Redis/queue, Ollama — kept distinct
from the product eval-health metric (ADR 0006). Each check is a small,
dependency-injected function returning a :class:`CheckResult`, so the
readiness probe is testable without real infrastructure.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from arq.constants import default_queue_name, health_check_key_suffix
from sqlalchemy import text

from pulsegraph.db.models import SourceHealth
from pulsegraph.domain.enums import SourceStatus

# arq writes the queue as a sorted set and refreshes a health-check key
# with a short TTL while the worker is alive (see arq.constants).
_QUEUE_KEY = default_queue_name
_HEALTH_KEY = f"{default_queue_name}{health_check_key_suffix}"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of one dependency check."""

    name: str
    ok: bool
    detail: str | None = None


class _Pingable(Protocol):
    def ping(self) -> Any: ...


def check_database(db: Any) -> CheckResult:
    """Verify the database answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        return CheckResult("database", True)
    except Exception as exc:  # noqa: BLE001 - report any failure, never raise
        return CheckResult("database", False, str(exc))


def check_redis(client: _Pingable) -> CheckResult:
    """Verify Redis (the arq queue backend) responds to PING."""
    try:
        client.ping()
        return CheckResult("redis", True)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("redis", False, str(exc))


def check_ollama(
    base_url: str,
    *,
    get: Callable[..., httpx.Response] = httpx.get,
    timeout: float = 2.0,
) -> CheckResult:
    """Verify the local Ollama instance is reachable."""
    try:
        response = get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        return CheckResult("ollama", True)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("ollama", False, str(exc))


def summarize(results: list[CheckResult]) -> dict:
    """Fold per-dependency results into a readiness summary.

    ``status`` is ``ok`` only when every check passed, otherwise
    ``degraded`` — the signal a load balancer or operator alerts on.
    """
    healthy = all(r.ok for r in results)
    return {
        "status": "ok" if healthy else "degraded",
        "checks": {r.name: {"ok": r.ok, "detail": r.detail} for r in results},
    }


def queue_depth(client: Any) -> int:
    """Return the number of jobs currently in the arq queue."""
    return int(client.zcard(_QUEUE_KEY))


def worker_alive(client: Any) -> bool:
    """Whether a worker has refreshed its health-check key recently.

    arq keeps the key alive with a short TTL while running, so its
    presence means a worker is up; its absence means none is (ADR 0020).
    """
    return bool(client.exists(_HEALTH_KEY))


def queue_status(depth: int, worker_up: bool, backlog_threshold: int) -> dict:
    """Operational view of the queue (ADR 0020).

    ``worker_down`` and ``backlog`` are the operator alert signals: no
    worker draining the queue, or a backlog past the threshold.
    """
    return {
        "depth": depth,
        "worker_alive": worker_up,
        "worker_down": not worker_up,
        "backlog": depth >= backlog_threshold,
    }


def paused_sources(db: Any) -> list[str]:
    """Return the sources currently paused for drift (ADR 0010/0020).

    Filtered in Python too, so it is correct under the FakeSession test
    double whose ``filter`` is a no-op.
    """
    return [
        row.source
        for row in db.query(SourceHealth)
        .filter(SourceHealth.status == SourceStatus.PAUSED)
        .all()
        if row.status == SourceStatus.PAUSED
    ]


def spend_status(spend_usd: float, cap_usd: float, alert_ratio: float) -> dict:
    """Report cloud-model spend against the monthly cap (ADR 0008/0020).

    ``near_cap`` is the operator alert signal; ``over_cap`` means the cap
    is already reached and cloud calls are being refused.
    """
    ratio = spend_usd / cap_usd if cap_usd > 0 else 0.0
    return {
        "spend_usd": round(spend_usd, 6),
        "cap_usd": cap_usd,
        "ratio": round(ratio, 4),
        "near_cap": ratio >= alert_ratio,
        "over_cap": spend_usd >= cap_usd,
    }
