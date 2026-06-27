"""Tests for hybrid model routing decisions."""

from pulsegraph.domain.enums import ModelKind
from pulsegraph.pipeline.routing import (
    COMPLEX_CONTENT_LENGTH,
    TaskComplexity,
    choose_model,
    classify_complexity,
    should_fallback,
)

# --- complexity classification ---


def test_short_content_is_simple() -> None:
    assert classify_complexity("short") is TaskComplexity.SIMPLE


def test_long_content_is_complex() -> None:
    content = "x" * COMPLEX_CONTENT_LENGTH
    assert classify_complexity(content) is TaskComplexity.COMPLEX


# --- initial routing ---


def test_complex_task_uses_cloud_when_available() -> None:
    model = choose_model(TaskComplexity.COMPLEX, cloud_available=True)

    assert model is ModelKind.CLAUDE


def test_complex_task_stays_local_without_cloud() -> None:
    model = choose_model(TaskComplexity.COMPLEX, cloud_available=False)

    assert model is ModelKind.OLLAMA


def test_simple_task_always_local() -> None:
    model = choose_model(TaskComplexity.SIMPLE, cloud_available=True)

    assert model is ModelKind.OLLAMA


# --- fallback ---


def test_fallback_on_low_confidence() -> None:
    assert should_fallback(
        local_confidence=0.2, timed_out=False, cloud_available=True
    )


def test_fallback_on_timeout() -> None:
    assert should_fallback(
        local_confidence=0.9, timed_out=True, cloud_available=True
    )


def test_no_fallback_when_confident() -> None:
    assert not should_fallback(
        local_confidence=0.9, timed_out=False, cloud_available=True
    )


def test_no_fallback_without_cloud() -> None:
    assert not should_fallback(
        local_confidence=0.0, timed_out=True, cloud_available=False
    )
