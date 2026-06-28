"""Tests for operator alert routing (ADR 0020)."""

from pulsegraph.config import Settings
from pulsegraph.worker.alerts import send_operator_alert


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
