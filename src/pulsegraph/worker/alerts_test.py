"""Tests for operator alert routing (ADR 0020)."""

import fakeredis

from pulsegraph.api._fake import FakeSession
from pulsegraph.config import Settings
from pulsegraph.worker.alerts import push_operator_alerts, send_operator_alert


class _Response:
    def raise_for_status(self) -> None:
        pass


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)


def test_send_operator_alert_noop_without_url() -> None:
    sent = send_operator_alert(["worker down"], _settings(), post=_fail_post)
    assert sent is False


def test_send_operator_alert_noop_without_messages() -> None:
    settings = _settings(OPERATOR_WEBHOOK_URL="https://ops.example/hook")
    assert send_operator_alert([], settings, post=_fail_post) is False


def test_send_operator_alert_posts_payload() -> None:
    captured = {}

    def _post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["body"] = content
        captured["headers"] = headers
        return _Response()

    settings = _settings(OPERATOR_WEBHOOK_URL="https://ops.example/hook")
    sent = send_operator_alert(
        ["worker down", "backlog: 200"], settings, post=_post
    )

    assert sent is True
    assert captured["url"] == "https://ops.example/hook"
    assert b"worker down" in captured["body"]
    assert "X-PulseGraph-Signature" not in captured["headers"]


def test_send_operator_alert_signs_when_secret_set() -> None:
    captured = {}

    def _post(url, *, content, headers, timeout):
        captured["headers"] = headers
        return _Response()

    settings = _settings(
        OPERATOR_WEBHOOK_URL="https://ops.example/hook",
        OPERATOR_WEBHOOK_SECRET="s3cret",
    )
    send_operator_alert(["worker down"], settings, post=_post)

    signature = captured["headers"]["X-PulseGraph-Signature"]
    assert signature.startswith("sha256=")


def _fail_post(*args, **kwargs):  # pragma: no cover - must never be called
    raise AssertionError("post should not be called")


# --- push_operator_alerts (throttle/dedup, ADR 0020) ------------------------


def _healthy_summary() -> dict:
    return {
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


def _worker_down_summary() -> dict:
    summary = _healthy_summary()
    summary["queue"] = {"depth": 5, "worker_down": True, "backlog": False}
    return summary


def _stub_summary(monkeypatch, summary: dict) -> None:
    monkeypatch.setattr(
        "pulsegraph.worker.alerts.operational_summary",
        lambda *args, **kwargs: summary,
    )


def _stub_send(monkeypatch) -> list[list[str]]:
    sent_batches: list[list[str]] = []

    def _fake_send(messages, settings):
        sent_batches.append(list(messages))
        return True

    monkeypatch.setattr(
        "pulsegraph.worker.alerts.send_operator_alert", _fake_send
    )
    return sent_batches


def test_push_operator_alerts_noop_when_healthy(monkeypatch) -> None:
    _stub_summary(monkeypatch, _healthy_summary())
    sent_batches = _stub_send(monkeypatch)
    r = fakeredis.FakeRedis(decode_responses=True)

    result = push_operator_alerts(FakeSession(), r, _settings())

    assert result == {"alerts": 0, "throttled": 0, "sent": False}
    assert sent_batches == []


def test_push_operator_alerts_sends_on_first_fire(monkeypatch) -> None:
    _stub_summary(monkeypatch, _worker_down_summary())
    sent_batches = _stub_send(monkeypatch)
    r = fakeredis.FakeRedis(decode_responses=True)

    result = push_operator_alerts(FakeSession(), r, _settings())

    assert result == {"alerts": 1, "throttled": 0, "sent": True}
    assert len(sent_batches) == 1
    assert "no worker" in sent_batches[0][0]


def test_push_operator_alerts_throttles_repeat_within_window(
    monkeypatch,
) -> None:
    _stub_summary(monkeypatch, _worker_down_summary())
    sent_batches = _stub_send(monkeypatch)
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = _settings()

    push_operator_alerts(FakeSession(), r, settings)
    result = push_operator_alerts(FakeSession(), r, settings)

    assert result == {"alerts": 1, "throttled": 1, "sent": False}
    assert len(sent_batches) == 1


def test_push_operator_alerts_resends_after_recovery_and_new_incident(
    monkeypatch,
) -> None:
    sent_batches = _stub_send(monkeypatch)
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = _settings()
    db = FakeSession()

    _stub_summary(monkeypatch, _worker_down_summary())
    push_operator_alerts(db, r, settings)  # incident #1: sent

    _stub_summary(monkeypatch, _healthy_summary())
    push_operator_alerts(db, r, settings)  # resolved: clears the window

    _stub_summary(monkeypatch, _worker_down_summary())
    result = push_operator_alerts(db, r, settings)  # incident #2

    assert result == {"alerts": 1, "throttled": 0, "sent": True}
    assert len(sent_batches) == 2


def _stub_send_raises(monkeypatch) -> None:
    def _raise(messages, settings):
        raise RuntimeError("operator endpoint down")

    monkeypatch.setattr("pulsegraph.worker.alerts.send_operator_alert", _raise)


def test_push_operator_alerts_retries_after_delivery_failure(
    monkeypatch,
) -> None:
    # A transient operator-webhook outage must not silently swallow the
    # incident for a full cooldown window -- the next sweep has to retry
    # instead of the failed attempt counting as "already alerted."
    _stub_summary(monkeypatch, _worker_down_summary())
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = _settings()
    db = FakeSession()

    _stub_send_raises(monkeypatch)
    round1 = push_operator_alerts(db, r, settings)
    assert round1 == {"alerts": 1, "throttled": 0, "sent": False}

    sent_batches = _stub_send(monkeypatch)
    round2 = push_operator_alerts(db, r, settings)

    assert round2 == {"alerts": 1, "throttled": 0, "sent": True}
    assert len(sent_batches) == 1


def test_push_operator_alerts_kinds_throttle_independently(
    monkeypatch,
) -> None:
    sent_batches = _stub_send(monkeypatch)
    r = fakeredis.FakeRedis(decode_responses=True)
    settings = _settings()
    db = FakeSession()

    _stub_summary(monkeypatch, _worker_down_summary())
    push_operator_alerts(db, r, settings)  # worker_down: sent

    both_firing = _worker_down_summary()
    both_firing["queue"]["backlog"] = True
    both_firing["queue"]["depth"] = 200
    _stub_summary(monkeypatch, both_firing)
    result = push_operator_alerts(db, r, settings)

    assert result == {"alerts": 2, "throttled": 1, "sent": True}
    assert len(sent_batches) == 2
    assert "backlog" in sent_batches[1][0]
