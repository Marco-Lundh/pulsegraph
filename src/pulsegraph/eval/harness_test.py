"""Tests for the offline eval harness and release gate (ADR 0012)."""

from pulsegraph.domain.enums import SourceKind
from pulsegraph.eval.golden import GoldenExample, load_all_golden
from pulsegraph.eval.harness import (
    EvalMetrics,
    Prediction,
    Thresholds,
    evaluate_dataset,
    find_regressions,
    make_offline_predictor,
)


def _ex(content: str, label: bool) -> GoldenExample:
    return GoldenExample(SourceKind.JOBTECH, content, label)


# --- evaluate_dataset ------------------------------------------------------


def test_evaluate_dataset_computes_metrics() -> None:
    preds = {
        "a": Prediction(True, 0.9),  # label True  -> TP
        "b": Prediction(False, 0.3),  # label True  -> FN
        "c": Prediction(True, 0.6),  # label False -> FP
        "d": Prediction(False, 0.8),  # label False -> TN
    }
    examples = [
        _ex("a", True),
        _ex("b", True),
        _ex("c", False),
        _ex("d", False),
    ]

    m = evaluate_dataset(SourceKind.JOBTECH, examples, lambda c: preds[c])

    assert m.precision == 0.5
    assert m.recall == 0.5
    assert m.f1 == 0.5
    assert m.accuracy == 0.5
    assert m.calibration_error == 0.3
    assert m.n == 4


def test_evaluate_dataset_perfect_predictor() -> None:
    examples = [_ex("x", True), _ex("y", False)]

    def predict(content: str) -> Prediction:
        return Prediction(content == "x", 1.0)

    m = evaluate_dataset(SourceKind.JOBTECH, examples, predict)
    assert m.f1 == 1.0
    assert m.calibration_error == 0.0


# --- find_regressions ------------------------------------------------------


def _metrics(**kw) -> EvalMetrics:
    base = {
        "source": SourceKind.JOBTECH,
        "n": 10,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "accuracy": 1.0,
        "calibration_error": 0.1,
    }
    base.update(kw)
    return EvalMetrics(**base)


def test_find_regressions_none_when_above_thresholds() -> None:
    assert find_regressions([_metrics()], Thresholds()) == []


def test_find_regressions_flags_low_f1() -> None:
    reasons = find_regressions([_metrics(f1=0.4)], Thresholds())
    assert any("F1" in r for r in reasons)


def test_find_regressions_flags_poor_calibration() -> None:
    reasons = find_regressions([_metrics(calibration_error=0.9)], Thresholds())
    assert any("calibration" in r for r in reasons)


# --- offline predictor -----------------------------------------------------


def test_offline_predictor_notifies_on_long_relevant_item() -> None:
    predict = make_offline_predictor()
    long_item = "A detailed and substantial posting. " * 12
    assert predict(long_item).should_notify is True


def test_offline_predictor_skips_short_item() -> None:
    predict = make_offline_predictor()
    assert predict("Too short to matter.").should_notify is False


# --- the bundled golden datasets are the regression baseline ---------------


def test_bundled_golden_datasets_pass_the_gate() -> None:
    predict = make_offline_predictor()
    datasets = load_all_golden()
    assert set(datasets) == {
        SourceKind.JOBTECH,
        SourceKind.RIKSDAGEN,
        SourceKind.ENTSOE,
    }

    metrics = [
        evaluate_dataset(source, examples, predict)
        for source, examples in datasets.items()
    ]
    assert find_regressions(metrics, Thresholds()) == []
