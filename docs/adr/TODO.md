# pulsegraph — TODO

Known follow-ups, deferred from their originating ADR. Add new
decisions/ADRs above this line as they arise.

- **No retry cap on digest delivery (ADR 0016).** `send_digests` now
  correctly leaves a user's notifications `PENDING` for retry when their
  push fails (fixed), but there is no give-up threshold: a permanently
  broken channel (e.g. a dead webhook URL) means that user's `PENDING`
  queue grows every day forever. Needs a dead-letter path or an
  attempt-count column before this is production-safe for a user who
  never fixes a broken destination.

- **Operator alerts have no throttle/dedup (ADR 0020).** `worker/alerts.py`
  re-sends every firing alert on each 15-minute sweep for as long as the
  condition persists (e.g. a worker that stays down triggers a fresh
  alert every 15 minutes indefinitely, not just once).

- **Offline eval harness (ADR 0012) not yet run against the real model.**
  The golden datasets and CI gate (`scripts/offline_eval.py`) only
  exercise the offline/keyword predictor. Running the harness against
  the real Ollama/Claude routing and empirically tuning `EVAL_MIN_F1`
  is still open.

- **No real CD/deploy pipeline (ADR 0017).** CI (`.github/workflows/ci.yml`)
  covers lint, unit tests, the offline eval gate, the e2e smoke test, and
  a dashboard lint/typecheck/build job — but nothing in the pipeline
  actually deploys anywhere.
