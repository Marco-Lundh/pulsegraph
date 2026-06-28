#!/usr/bin/env python
"""Offline evaluation release gate (ADR 0012/0019).

Runs the bundled golden datasets through the offline predictor, prints a
per-source metrics report, and exits non-zero if any metric regresses
past the configured thresholds. Wired into CI as a release gate.

    uv run python scripts/offline_eval.py
"""

import sys

from pulsegraph.config import get_settings
from pulsegraph.eval.golden import load_all_golden
from pulsegraph.eval.harness import (
    Thresholds,
    evaluate_dataset,
    find_regressions,
    make_offline_predictor,
)


def run_gate() -> int:
    """Return 0 if every dataset clears the thresholds, 1 otherwise."""
    settings = get_settings()
    thresholds = Thresholds(min_f1=settings.eval_min_f1)
    predict = make_offline_predictor()
    datasets = load_all_golden()

    if not datasets:
        print("no golden datasets found", file=sys.stderr)
        return 1

    metrics = [
        evaluate_dataset(source, examples, predict)
        for source, examples in sorted(datasets.items())
    ]
    for m in metrics:
        print(
            f"{m.source.value:10s} n={m.n:<3d} "
            f"f1={m.f1:.3f} precision={m.precision:.3f} "
            f"recall={m.recall:.3f} acc={m.accuracy:.3f} "
            f"calib={m.calibration_error:.3f}"
        )

    regressions = find_regressions(metrics, thresholds)
    if regressions:
        print("\nRELEASE GATE FAILED:", file=sys.stderr)
        for reason in regressions:
            print(f"  - {reason}", file=sys.stderr)
        return 1

    print("\nRelease gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_gate())
