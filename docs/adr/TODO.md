# pulsegraph — TODO

Known follow-ups, deferred from their originating ADR. Add new
decisions/ADRs above this line as they arise.

The list is grouped by how visible the gap is: robustness/hardening
follow-ups, then larger deferred work. Each item cites the ADR it traces
to. (The backend/UI parity gaps — Tier 2 — are now closed: model used and
per-item eval on the run detail page, the LangSmith trace id on `RunOut`,
the dashboard notification-channel type, and an admin cost-ledger view.)

## Robustness & hardening

- **No worker retry/backoff (ADR 0015).** `WorkerSettings` sets no
  `max_tries`/retry/backoff, and a permanently failing watch is marked
  FAILED but never paused/deactivated. The per-user hourly rate limit is
  also enforced inside the task rather than at enqueue time.

- **Instant delivery is fire-and-forget (ADR 0016).** Only the digest path
  tracks per-notification status and retries. Instant email/webhook sends
  log failures but write no per-channel `Notification` row, status, or
  retry (only the dashboard channel gets a row).

- **LLM input hardening is partial (ADR 0013).** `sanitize_text` strips
  control chars and caps length but does not neutralize known injection
  markers, and the Ollama client concatenates untrusted content into the
  prompt string rather than using role-tagged instruction/data separation
  (the Claude client does separate system/user).

- **Auth endpoints are not rate-limited (ADR 0021).** `login`/`register`
  have no brute-force protection; `check_rate` is used only by the worker.

- **GDPR gaps (ADR 0018).** Consent / lawful basis is not recorded at
  signup (no field on `User`), and erasure/retention never touches
  external LangSmith traces — only `Item` and `PipelineRun` are purged.

- **Embedding version safety is incomplete (ADR 0014).** `embedding_model`
  is recorded per item, but there is no re-embedding migration/job, the
  dimension is hardcoded (`Vector(768)` / `EMBEDDING_DIM = 768`), and no
  similarity query is ever run (dedup is content-hash only).

- **No graph checkpointer (ADR 0001).** `graph.compile()` runs without a
  checkpointer, so the ADR's state persistence / time-travel / rollback
  are not available at runtime.

- **Prompt registry is provenance-only (ADR 0011).** Every `Analysis` now
  pins the active analyzer `prompt_id` and records its `params`, and the
  local client's template is seeded from the same constant it runs. The
  model clients still hold their prompt text in code rather than loading
  the active template from the registry at runtime, and there is no CRUD /
  admin surface for editing or versioning prompts.

- **Drift recovery is manual (ADR 0010).** A source paused for schema
  drift is resumed only by the admin `POST /admin/source-health/{source}/resume`
  action (or a plugin fix); there is no automatic health re-probe that
  clears the pause once the upstream schema returns.

- **Short/default secrets are not validated for prod (ADR 0009/0021).**
  `JWT_SECRET_KEY` defaults to `"dev-secret-change-in-prod"` (25 bytes,
  below the 32-byte HMAC-SHA256 recommendation) with no startup check that
  a real secret is set when `PULSEGRAPH_ENV != "local"`.

## Larger deferred work

- **Offline eval not yet tuned against the real model (ADR 0012).** The
  golden datasets, the CI release gate (`scripts/offline_eval.py`), and the
  review → dataset growth job (`scripts/grow_golden.py`) all run against
  the deterministic offline predictor. Running the harness against the real
  Ollama/Claude routing and empirically tuning `EVAL_MIN_F1` is still open
  (the harness's predictor is already injectable for this).

- **No real CD/deploy pipeline (ADR 0017).** CI (`.github/workflows/ci.yml`)
  covers lint, unit tests, the offline eval gate, the e2e smoke test, and a
  dashboard lint/typecheck/build job — but nothing deploys anywhere, there
  is no staging/production split, and "migrations applied automatically on
  deploy" with a documented rollback path is unimplemented.
