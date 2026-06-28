"""Tests for the liveness and readiness endpoints (ADR 0020)."""

from fastapi.testclient import TestClient

from pulsegraph.api.app import create_app
from pulsegraph.api.deps import get_db
from pulsegraph.api.health import CheckResult
from pulsegraph.api.routers import meta


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: (yield None)
    return TestClient(app)


def _patch_checks(monkeypatch, *, db=True, redis=True, ollama=True) -> None:
    monkeypatch.setattr(
        meta, "check_database", lambda _db: CheckResult("database", db)
    )
    monkeypatch.setattr(
        meta, "check_redis", lambda _r: CheckResult("redis", redis)
    )
    monkeypatch.setattr(
        meta, "check_ollama", lambda _url: CheckResult("ollama", ollama)
    )


def test_health_liveness() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_ok_when_all_checks_pass(monkeypatch) -> None:
    _patch_checks(monkeypatch)
    resp = _client().get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_503_when_a_check_fails(monkeypatch) -> None:
    _patch_checks(monkeypatch, redis=False)
    resp = _client().get("/health/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["ok"] is False
