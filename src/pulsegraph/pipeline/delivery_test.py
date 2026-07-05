"""Tests for the real email and webhook notification sinks (ADR 0016)."""

import hashlib
import hmac
import json
from email.message import EmailMessage

import pytest

from pulsegraph.pipeline.contracts import NotificationDraft
from pulsegraph.pipeline.delivery import (
    EmailSink,
    MultiSink,
    WebhookSink,
)


def _draft(user_id: str = "u1") -> NotificationDraft:
    return NotificationDraft(
        user_id=user_id,
        title="New job at ACME",
        body="ACME is hiring a Python engineer in Stockholm.",
        dedup_key="jobtech:42",
        labels=("python", "remote"),
    )


# --- EmailSink -------------------------------------------------------------


class _RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def test_email_sink_sends_message_to_resolved_recipient() -> None:
    transport = _RecordingTransport()
    sink = EmailSink(
        sender="alerts@pulsegraph.io",
        transport=transport,
        resolve=lambda user_id: "user@example.com",
    )

    sink.send(_draft())

    assert len(transport.sent) == 1
    message = transport.sent[0]
    assert message["To"] == "user@example.com"
    assert message["From"] == "alerts@pulsegraph.io"
    assert message["Subject"] == "New job at ACME"
    assert "Python engineer" in message.get_content()


def test_email_sink_skips_when_no_recipient() -> None:
    transport = _RecordingTransport()
    sink = EmailSink(
        sender="alerts@pulsegraph.io",
        transport=transport,
        resolve=lambda user_id: None,
    )

    sink.send(_draft())

    assert transport.sent == []


# --- WebhookSink -----------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _RecordingPoster:
    def __init__(self, status_code: int = 200) -> None:
        self.calls: list[dict] = []
        self._status_code = status_code

    def __call__(self, url, *, content, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "content": content,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self._status_code)


def test_webhook_sink_posts_json_payload() -> None:
    poster = _RecordingPoster()
    sink = WebhookSink(
        resolve=lambda user_id: "https://hook.example/x",
        post=poster,
    )

    sink.send(_draft())

    assert len(poster.calls) == 1
    call = poster.calls[0]
    assert call["url"] == "https://hook.example/x"
    payload = json.loads(call["content"])
    assert payload["title"] == "New job at ACME"
    assert payload["dedup_key"] == "jobtech:42"
    assert payload["labels"] == ["python", "remote"]
    assert payload["user_id"] == "u1"


def test_webhook_sink_signs_payload_when_secret_set() -> None:
    poster = _RecordingPoster()
    sink = WebhookSink(
        resolve=lambda user_id: "https://hook.example/x",
        post=poster,
        secret="s3cret",
    )

    sink.send(_draft())

    call = poster.calls[0]
    expected = hmac.new(b"s3cret", call["content"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-PulseGraph-Signature"] == f"sha256={expected}"


def test_webhook_sink_skips_when_no_url() -> None:
    poster = _RecordingPoster()
    sink = WebhookSink(resolve=lambda user_id: None, post=poster)

    sink.send(_draft())

    assert poster.calls == []


def test_webhook_sink_raises_on_http_error() -> None:
    poster = _RecordingPoster(status_code=500)
    sink = WebhookSink(
        resolve=lambda user_id: "https://hook.example/x",
        post=poster,
    )

    with pytest.raises(RuntimeError):
        sink.send(_draft())


# --- MultiSink -------------------------------------------------------------


class _CollectingSink:
    def __init__(self) -> None:
        self.received: list[NotificationDraft] = []

    def send(self, draft: NotificationDraft) -> None:
        self.received.append(draft)


class _FailingSink:
    def send(self, draft: NotificationDraft) -> None:
        raise RuntimeError("channel down")


def test_multi_sink_fans_out_to_all_children() -> None:
    a = _CollectingSink()
    b = _CollectingSink()
    sink = MultiSink([a, b])

    draft = _draft()
    sink.send(draft)

    assert a.received == [draft]
    assert b.received == [draft]


def test_multi_sink_isolates_a_failing_channel() -> None:
    good = _CollectingSink()
    sink = MultiSink([_FailingSink(), good])

    draft = _draft()
    # A failing channel must not raise or block the healthy channel.
    sink.send(draft)

    assert good.received == [draft]


def test_multi_sink_send_returns_true_when_all_succeed() -> None:
    sink = MultiSink([_CollectingSink(), _CollectingSink()])
    assert sink.send(_draft()) is True


def test_multi_sink_send_returns_false_when_any_channel_fails() -> None:
    # A caller that needs to know delivery actually happened (the digest
    # job, ADR 0016) relies on this to decide whether to retry.
    sink = MultiSink([_CollectingSink(), _FailingSink()])
    assert sink.send(_draft()) is False


def test_multi_sink_send_returns_true_with_no_channels() -> None:
    assert MultiSink([]).send(_draft()) is True


# --- MultiSink.send_detailed -------------------------------------------


def test_multi_sink_send_detailed_all_ok_when_all_succeed() -> None:
    sink = MultiSink([_CollectingSink(), _CollectingSink()])
    result = sink.send_detailed(_draft())
    assert result.all_ok is True
    assert result.any_ok is True


def test_multi_sink_send_detailed_any_ok_true_on_partial_failure() -> None:
    # One channel down, one channel up: the destination is not fully
    # dead, so callers (the digest retry cap, ADR 0016) must be able to
    # tell this apart from every channel failing.
    sink = MultiSink([_CollectingSink(), _FailingSink()])
    result = sink.send_detailed(_draft())
    assert result.all_ok is False
    assert result.any_ok is True


def test_multi_sink_send_detailed_any_ok_false_when_all_fail() -> None:
    sink = MultiSink([_FailingSink(), _FailingSink()])
    result = sink.send_detailed(_draft())
    assert result.all_ok is False
    assert result.any_ok is False


def test_multi_sink_send_detailed_true_with_no_channels() -> None:
    result = MultiSink([]).send_detailed(_draft())
    assert result.all_ok is True
    assert result.any_ok is True
