# pulsegraph — TODO

Known follow-ups, deferred from their originating ADR. Add new
decisions/ADRs above this line as they arise.

- **Offline eval harness (ADR 0012) not yet run against the real model.**
  The golden datasets and CI gate (`scripts/offline_eval.py`) only
  exercise the offline/keyword predictor. Running the harness against
  the real Ollama/Claude routing and empirically tuning `EVAL_MIN_F1`
  is still open.

- **No real CD/deploy pipeline (ADR 0017).** CI (`.github/workflows/ci.yml`)
  covers lint, unit tests, the offline eval gate, the e2e smoke test, and
  a dashboard lint/typecheck/build job — but nothing in the pipeline
  actually deploys anywhere.
