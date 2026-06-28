"""Tests for operational health checks and spend signal (ADR 0020)."""

import fakeredis

from pulsegraph.api._fake import FakeSession
from pulsegraph.api.health import (
    CheckResult,
    check_database,
    check_ollama,
    check_redis,
    paused_sources,
    queue_depth,
    queue_status,
    spend_status,
    summarize,
    worker_alive,
)
from pulsegraph.db.models import SourceHealth
from pulsegraph.domain.enums import SourceKind, SourceStatus


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
