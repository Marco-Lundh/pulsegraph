"""Offline eval harness and release gate (ADR 0012).

Runs a golden dataset (ground-truth notify-or-not labels) through a
predictor and reports metrics per source type: notify precision/recall/
F1, accuracy, and a confidence-calibration error. ``find_regressions``
turns those metrics into a pass/fail release gate (ADR 0019).

The predictor is injectable: the bundled :func:`make_offline_predictor`
wires the deterministic offline adapters so the gate runs in CI with no
model, exercising the real routing and evaluation gate (ADR 0002/0006); a
real deployment can run the same harness against the live model.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pulsegraph.domain.enums import EvalStatus, SourceKind
from pulsegraph.eval.golden import GoldenExample
from pulsegraph.pipeline.agents import PipelineDeps, _analyze_one, _evaluate
from pulsegraph.pipeline.local import (
    DictSourceRegistry,
    HashingEmbedder,
    InMemorySink,
    KeywordModelClient,
)


@dataclass(frozen=True, slots=True)
class Prediction:
    """A predictor's verdict on one item."""

    should_notify: bool
    confidence: float


Predictor = Callable[[str], Prediction]


@dataclass(frozen=True, slots=True)
class EvalMetrics:
    """Quality metrics for one source type's golden dataset."""

    source: SourceKind
    n: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    calibration_error: float


@dataclass(frozen=True, slots=True)
class Thresholds:
    """The minimum metrics a release must meet (ADR 0012/0019)."""

    min_f1: float = 0.7
    min_precision: float = 0.7
    min_recall: float = 0.7
    max_calibration_error: float = 0.4


def _ratio(numerator: int, denominator: int) -> float:
    """Guard against an empty denominator (no positives to judge)."""
    return numerator / denominator if denominator else 1.0


def evaluate_dataset(
    source: SourceKind,
    examples: list[GoldenExample],
    predict: Predictor,
) -> EvalMetrics:
    """Score *predict* against the golden *examples* for one source."""
    tp = fp = fn = tn = 0
    calibration_total = 0.0
    for example in examples:
        prediction = predict(example.content)
        correct = prediction.should_notify == example.should_notify
        calibration_total += abs(
            prediction.confidence - (1.0 if correct else 0.0)
        )
        if prediction.should_notify and example.should_notify:
            tp += 1
        elif prediction.should_notify:
            fp += 1
        elif example.should_notify:
            fn += 1
        else:
            tn += 1

    n = len(examples)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return EvalMetrics(
        source=source,
        n=n,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        accuracy=round(_ratio(tp + tn, n), 4),
        calibration_error=round(calibration_total / n if n else 0.0, 4),
    )


def find_regressions(
    metrics: list[EvalMetrics], thresholds: Thresholds
) -> list[str]:
    """Return a human-readable reason for every metric below threshold."""
    reasons = []
    for m in metrics:
        if m.f1 < thresholds.min_f1:
            reasons.append(f"{m.source}: F1 {m.f1} < {thresholds.min_f1}")
        if m.precision < thresholds.min_precision:
            reasons.append(
                f"{m.source}: precision {m.precision} "
                f"< {thresholds.min_precision}"
            )
        if m.recall < thresholds.min_recall:
            reasons.append(
                f"{m.source}: recall {m.recall} < {thresholds.min_recall}"
            )
        if m.calibration_error > thresholds.max_calibration_error:
            reasons.append(
                f"{m.source}: calibration {m.calibration_error} "
                f"> {thresholds.max_calibration_error}"
            )
    return reasons


def make_offline_predictor() -> Predictor:
    """A deterministic predictor wired to the offline adapters.

    Runs the real Analyzer routing and Evaluator gate (ADR 0002/0006) on
    the local ``KeywordModelClient``, so the gate guards that logic
    without needing Ollama or a cloud key.
    """
    deps = PipelineDeps(
        registry=DictSourceRegistry(),
        embedder=HashingEmbedder(),
        model=KeywordModelClient(),
        sink=InMemorySink(),
        cloud_available=False,
    )

    def predict(content: str) -> Prediction:
        result = _analyze_one(deps, content)
        status, _ = _evaluate(deps, result)
        return Prediction(
            should_notify=status is EvalStatus.APPROVED,
            confidence=result.confidence,
        )

    return predict
