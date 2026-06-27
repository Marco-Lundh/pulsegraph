"""Hybrid model routing decisions (ADR 0002).

Pure decision functions, isolated from any model client so the
cost-optimization logic is explicit and testable. The Analyzer wires
these to real clients.
"""

from enum import StrEnum

from pulsegraph.domain.enums import ModelKind

DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Content at or above this length is treated as complex enough to
# prefer the cloud model when one is available (ADR 0002).
COMPLEX_CONTENT_LENGTH = 1_500


class TaskComplexity(StrEnum):
    """How demanding an analysis task is (ADR 0002)."""

    SIMPLE = "simple"
    COMPLEX = "complex"


def classify_complexity(
    content: str, threshold: int = COMPLEX_CONTENT_LENGTH
) -> TaskComplexity:
    """Classify a task by content length.

    A deterministic length heuristic keeps routing explainable and
    testable; longer items carry more nuance and benefit from the
    stronger model.
    """
    if len(content) >= threshold:
        return TaskComplexity.COMPLEX
    return TaskComplexity.SIMPLE


def choose_model(
    complexity: TaskComplexity, cloud_available: bool
) -> ModelKind:
    """Pick the initial model for a task.

    Complex tasks prefer the cloud model when it is available;
    everything else runs on the free local model.
    """
    if complexity is TaskComplexity.COMPLEX and cloud_available:
        return ModelKind.CLAUDE
    return ModelKind.OLLAMA


def should_fallback(
    local_confidence: float,
    timed_out: bool,
    cloud_available: bool,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> bool:
    """Whether a local result should be re-routed to the cloud model.

    Falls back when the cloud model is available and the local run
    either timed out or returned confidence below the threshold.
    """
    if not cloud_available:
        return False
    return timed_out or local_confidence < threshold
