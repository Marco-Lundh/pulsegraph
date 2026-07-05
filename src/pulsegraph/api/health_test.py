"""Tests for operational health checks and spend signal (ADR 0020)."""

import datetime
import uuid

import fakeredis

from pulsegraph.api._fake import FakeSession
from pulsegraph.api.health import (
    ALERT_KINDS,
    CheckResult,
    check_database,
    check_ollama,
    check_redis,
    collect_alerts,
    latency_stats,
    operational_summary,
    paused_sources,
    queue_depth,
    queue_status,
    run_latencies,
    spend_status,
    summarize,
    worker_alive,
)
from pulsegraph.config import Settings
from pulsegraph.db.models import PipelineRun, SourceHealth
from pulsegraph.domain.enums import RunStatus, SourceKind, SourceStatus

_NOW = datetime.datetime(2026, 6, 28, 12, 0, tzinfo=datetime.UTC)


class _OkResponse:
    def raise_for_status(self) -> None:
        pass


class _FailResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("502")


# --- check_database ---


def test_check_database_ok() -> None:
    class _DB:
        def execute(self, _query: object) -> None:
            pass

    result = check_database(_DB())
    assert result == CheckResult("database", True)


def test_check_database_failure_is_captured() -> None:
    class _DB:
        def execute(self, _query: object) -> None:
            raise RuntimeError("connection refused")

    result = check_database(_DB())
    assert result.ok is False
    assert "connection refused" in result.detail


# --- check_redis ---


def test_check_redis_ok() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    assert check_redis(r) == CheckResult("redis", True)


def test_check_redis_failure_is_captured() -> None:
    class _R:
        def ping(self) -> None:
            raise ConnectionError("down")

    result = check_redis(_R())
    assert result.ok is False
    assert "down" in result.detail


# --- check_ollama ---


def test_check_ollama_ok() -> None:
    result = check_ollama("http://x:11434", get=lambda *a, **k: _OkResponse())
    assert result == CheckResult("ollama", True)


def test_check_ollama_failure_is_captured() -> None:
    result = check_ollama(
        "http://x:11434", get=lambda *a, **k: _FailResponse()
    )
    assert result.ok is False


# --- summarize ---


def test_summarize_ok_when_all_pass() -> None:
    summary = summarize([CheckResult("a", True), CheckResult("b", True)])
    assert summary["status"] == "ok"
    assert summary["checks"]["a"]["ok"] is True


def test_summarize_degraded_when_any_fails() -> None:
    summary = summarize(
        [CheckResult("a", True), CheckResult("b", False, "boom")]
    )
    assert summary["status"] == "degraded"
    assert summary["checks"]["b"]["detail"] == "boom"


# --- queue depth / worker liveness ---


def test_queue_depth_counts_queued_jobs() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    r.zadd("arq:queue", {"job1": 1.0, "job2": 2.0})
    assert queue_depth(r) == 2


def test_queue_depth_zero_when_empty() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    assert queue_depth(r) == 0


def test_worker_alive_true_when_health_key_present() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    r.set("arq:queue:health-check", "ok")
    assert worker_alive(r) is True


def test_worker_alive_false_when_absent() -> None:
    r = fakeredis.FakeRedis(decode_responses=True)
    assert worker_alive(r) is False


# --- queue_status ---


def test_queue_status_healthy() -> None:
    status = queue_status(depth=5, worker_up=True, backlog_threshold=100)
    assert status == {
        "depth": 5,
        "worker_alive": True,
        "worker_down": False,
        "backlog": False,
    }


def test_queue_status_flags_backlog_and_down_worker() -> None:
    status = queue_status(depth=150, worker_up=False, backlog_threshold=100)
    assert status["backlog"] is True
    assert status["worker_down"] is True


# --- paused_sources ---


def test_paused_sources_lists_only_paused() -> None:
    paused = SourceHealth(
        source=SourceKind.JOBTECH, status=SourceStatus.PAUSED
    )
    db = FakeSession(paused)
    assert paused_sources(db) == [SourceKind.JOBTECH]


def test_paused_sources_excludes_healthy() -> None:
    healthy = SourceHealth(
        source=SourceKind.RIKSDAGEN, status=SourceStatus.HEALTHY
    )
    db = FakeSession(healthy)
    assert paused_sources(db) == []


# --- spend_status ---


def test_spend_status_below_threshold() -> None:
    s = spend_status(spend_usd=2.0, cap_usd=10.0, alert_ratio=0.8)
    assert s["ratio"] == 0.2
    assert s["near_cap"] is False
    assert s["over_cap"] is False


def test_spend_status_near_cap() -> None:
    s = spend_status(spend_usd=8.5, cap_usd=10.0, alert_ratio=0.8)
    assert s["near_cap"] is True
    assert s["over_cap"] is False


def test_spend_status_over_cap() -> None:
    s = spend_status(spend_usd=10.0, cap_usd=10.0, alert_ratio=0.8)
    assert s["near_cap"] is True
    assert s["over_cap"] is True


def test_spend_status_handles_zero_cap() -> None:
    s = spend_status(spend_usd=1.0, cap_usd=0.0, alert_ratio=0.8)
    assert s["ratio"] == 0.0
    assert s["over_cap"] is True


# --- latency ---


def _run(age_hours: float, duration_s: float) -> PipelineRun:
    started = _NOW - datetime.timedelta(hours=age_hours)
    return PipelineRun(
        id=uuid.uuid4(),
        watch_id=uuid.uuid4(),
        status=RunStatus.SUCCEEDED,
        started_at=started,
        finished_at=started + datetime.timedelta(seconds=duration_s),
    )


def test_run_latencies_within_window() -> None:
    db = FakeSession(_run(1, 10.0), _run(2, 20.0))
    assert sorted(run_latencies(db, _NOW)) == [10.0, 20.0]


def test_run_latencies_excludes_old_runs() -> None:
    db = FakeSession(_run(1, 10.0), _run(48, 99.0))
    assert run_latencies(db, _NOW) == [10.0]


def test_latency_stats_empty() -> None:
    s = latency_stats([], alert_seconds=300)
    assert s == {
        "count": 0,
        "avg_seconds": 0.0,
        "p95_seconds": 0.0,
        "max_seconds": 0.0,
        "slow": False,
    }


def test_latency_stats_values_and_slow_flag() -> None:
    s = latency_stats([10.0, 20.0, 600.0], alert_seconds=300)
    assert s["count"] == 3
    assert s["max_seconds"] == 600.0
    assert s["p95_seconds"] == 600.0
    assert s["slow"] is True


# --- collect_alerts ---


def _summary(**overrides) -> dict:
    base = {
        "spend": {
            "spend_usd": 1.0,
            "ratio": 0.1,
            "near_cap": False,
            "over_cap": False,
        },
        "queue": {"depth": 0, "worker_down": False, "backlog": False},
        "sources": {"paused": [], "alert": False},
        "latency": {"p95_seconds": 1.0, "slow": False},
    }
    base.update(overrides)
    return base


def test_collect_alerts_empty_when_healthy() -> None:
    assert collect_alerts(_summary()) == []


def test_collect_alerts_flags_each_signal() -> None:
    summary = _summary(
        spend={
            "spend_usd": 11.0,
            "ratio": 1.1,
            "near_cap": True,
            "over_cap": True,
        },
        queue={"depth": 200, "worker_down": True, "backlog": True},
        sources={"paused": ["jobtech"], "alert": True},
        latency={"p95_seconds": 900.0, "slow": True},
    )
    alerts = collect_alerts(summary)
    joined = " ".join(a.message for a in alerts)
    assert "cost cap reached" in joined
    assert "no worker" in joined
    assert "backlog" in joined
    assert "paused" in joined
    assert "slow runs" in joined
    assert {a.kind for a in alerts} == {
        "spend_over_cap",
        "worker_down",
        "queue_backlog",
        "sources_paused",
        "slow_runs",
    }


def test_alert_kinds_covers_every_kind_collect_alerts_can_emit() -> None:
    # ALERT_KINDS is what worker.alerts iterates to clear a resolved
    # kind's cooldown window; if it ever drifts out of sync with the
    # kinds collect_alerts actually emits, that clearing silently stops
    # working for the missing kind. over_cap wins over near_cap (elif),
    # so a second summary exercises near_cap on its own.
    over_cap_summary = _summary(
        spend={
            "spend_usd": 11.0,
            "ratio": 1.1,
            "near_cap": True,
            "over_cap": True,
        },
        queue={"depth": 200, "worker_down": True, "backlog": True},
        sources={"paused": ["jobtech"], "alert": True},
        latency={"p95_seconds": 900.0, "slow": True},
    )
    near_cap_summary = _summary(
        spend={
            "spend_usd": 5.0,
            "ratio": 0.85,
            "near_cap": True,
            "over_cap": False,
        }
    )
    emitted_kinds = {a.kind for a in collect_alerts(over_cap_summary)} | {
        a.kind for a in collect_alerts(near_cap_summary)
    }
    assert emitted_kinds == set(ALERT_KINDS)


# --- operational_summary ---


def test_operational_summary_assembles_sections(monkeypatch) -> None:
    import pulsegraph.api.health as health_mod

    monkeypatch.setattr(health_mod, "get_monthly_cost", lambda _r: 2.0)
    r = fakeredis.FakeRedis(decode_responses=True)
    db = FakeSession()
    summary = operational_summary(db, r, Settings(_env_file=None))
    assert set(summary) == {"spend", "queue", "sources", "latency"}
    assert summary["queue"]["worker_alive"] is False
