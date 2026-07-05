"""Operational health checks and spend signal (ADR 0020).

Infrastructure liveness — database, Redis/queue, Ollama — kept distinct
from the product eval-health metric (ADR 0006). Each check is a small,
dependency-injected function returning a :class:`CheckResult`, so the
readiness probe is testable without real infrastructure.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple, Protocol

import httpx
from arq.constants import default_queue_name, health_check_key_suffix
from sqlalchemy import text

from pulsegraph.config import Settings
from pulsegraph.db.models import PipelineRun, SourceHealth
from pulsegraph.domain.enums import SourceStatus
from pulsegraph.redis_client import get_monthly_cost

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


def run_latencies(
    db: Any, now: datetime.datetime, lookback_hours: int = 24
) -> list[float]:
    """Return finished-run durations (seconds) within the lookback window.

    Filtered in Python too, so it is correct under the FakeSession test
    double whose ``filter`` is a no-op.
    """
    cutoff = now - datetime.timedelta(hours=lookback_hours)
    durations = []
    for run in (
        db.query(PipelineRun).filter(PipelineRun.finished_at >= cutoff).all()
    ):
        if run.finished_at is None or run.started_at is None:
            continue
        if run.finished_at < cutoff:
            continue
        durations.append((run.finished_at - run.started_at).total_seconds())
    return durations


def latency_stats(durations: list[float], alert_seconds: float) -> dict:
    """Summarize run durations with a p95 the operator alerts on."""
    if not durations:
        return {
            "count": 0,
            "avg_seconds": 0.0,
            "p95_seconds": 0.0,
            "max_seconds": 0.0,
            "slow": False,
        }
    ordered = sorted(durations)
    # Nearest-rank p95: the smallest value at or above the 95th percentile.
    index = max(0, round(0.95 * len(ordered)) - 1)
    p95 = ordered[index]
    return {
        "count": len(ordered),
        "avg_seconds": round(sum(ordered) / len(ordered), 2),
        "p95_seconds": round(p95, 2),
        "max_seconds": round(ordered[-1], 2),
        "slow": p95 > alert_seconds,
    }


def operational_summary(db: Any, redis: Any, settings: Settings) -> dict:
    """Assemble the full operator dashboard (ADR 0020).

    Shared by ``GET /admin/ops`` and the alert job so both read the same
    signals. Each section carries the alert flag operators watch.
    """
    paused = paused_sources(db)
    now = datetime.datetime.now(datetime.UTC)
    return {
        "spend": spend_status(
            get_monthly_cost(redis),
            settings.monthly_cost_cap_usd,
            settings.cost_alert_threshold_ratio,
        ),
        "queue": queue_status(
            queue_depth(redis),
            worker_alive(redis),
            settings.queue_backlog_alert_threshold,
        ),
        "sources": {"paused": paused, "alert": len(paused) > 0},
        "latency": latency_stats(
            run_latencies(db, now), settings.job_latency_alert_seconds
        ),
    }


class AlertSignal(NamedTuple):
    """One firing operator alert.

    ``kind`` is a stable identifier independent of the interpolated
    numbers in ``message`` (e.g. queue depth), so a throttle/dedup layer
    (``worker.alerts``, ADR 0020) can recognize "the same condition" run
    to run even though its message text changes.
    """

    kind: str
    message: str


# Every kind ``collect_alerts`` can produce. A throttle layer iterates
# this to know which cooldown windows to clear when a kind stops firing
# (ADR 0020) — keep in sync with the ``alerts.append`` calls below.
ALERT_KINDS = (
    "spend_over_cap",
    "spend_near_cap",
    "worker_down",
    "queue_backlog",
    "sources_paused",
    "slow_runs",
)


def collect_alerts(summary: dict) -> list[AlertSignal]:
    """Extract the currently-firing operator alerts from a summary.

    Empty when nothing is wrong — the alert job sends only when this is
    non-empty (ADR 0020).
    """
    alerts = []
    spend = summary["spend"]
    if spend["over_cap"]:
        alerts.append(
            AlertSignal(
                "spend_over_cap", f"cost cap reached: ${spend['spend_usd']}"
            )
        )
    elif spend["near_cap"]:
        alerts.append(
            AlertSignal(
                "spend_near_cap",
                f"spend near cap: {spend['ratio']:.0%} of the cap",
            )
        )

    queue = summary["queue"]
    if queue["worker_down"]:
        alerts.append(
            AlertSignal("worker_down", "no worker is draining the queue")
        )
    if queue["backlog"]:
        alerts.append(
            AlertSignal(
                "queue_backlog", f"queue backlog: {queue['depth']} jobs"
            )
        )

    if summary["sources"]["alert"]:
        paused = ", ".join(summary["sources"]["paused"])
        alerts.append(
            AlertSignal(
                "sources_paused", f"sources paused for drift: {paused}"
            )
        )

    if summary["latency"]["slow"]:
        alerts.append(
            AlertSignal(
                "slow_runs",
                f"slow runs: p95 {summary['latency']['p95_seconds']}s",
            )
        )
    return alerts
