"""Tests for untrusted-input sanitization."""

from pulsegraph.pipeline.sanitize import sanitize_text

# --- control characters ---


def test_strips_control_characters() -> None:
    assert sanitize_text("hi\x00\x07there") == "hithere"


def test_keeps_newlines_and_tabs() -> None:
    assert sanitize_text("a\nb\tc") == "a\nb\tc"


# --- length cap ---


def test_caps_length() -> None:
    assert len(sanitize_text("x" * 100, max_length=10)) == 10
