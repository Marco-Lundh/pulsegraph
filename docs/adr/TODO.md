# pulsegraph — TODO

Known follow-ups, deferred from their originating ADR. Add new
decisions/ADRs above this line as they arise.

The list is grouped by how visible the gap is: the robustness/hardening
follow-ups still open, then larger deferred work. Each item cites the ADR
it traces to. (Backend/UI parity — Tier 2 — is closed. The Tier 3
hardening subset is also done: worker retry/backoff + auto-deactivate of a
permanently failing watch (ADR 0015), auth-endpoint rate limiting (ADR
0021), LLM injection hardening — marker neutralization + Ollama
instruction/data separation (ADR 0013), automatic drift re-probe /
auto-resume (ADR 0010), production JWT-secret validation (ADR 0009/0021),
and GDPR consent captured at signup (ADR 0018). What remains below is the
harder-scoped work.)

## Robustness & hardening

- **Instant delivery is fire-and-forget (ADR 0016).** Only the digest path
  tracks per-notification status and retries. Instant email/webhook sends
  log failures but write no per-channel `Notification` row, status, or
  retry — only the dashboard channel gets a row. This is architectural, not
  a quick fix: the `notifications` unique constraint is `(user_id,
  dedup_key)` (one row per item, ADR 0016), so per-channel rows require
  adding `channel` to that constraint and reworking the dedup/digest
  idempotency that assumes a single row per item. Track with the other
  architectural follow-ups (0014 / 0001 / 0011).

- **LangSmith traces are not purged on erasure/retention (ADR 0018).**
  Consent at signup is now recorded, but a purged run's external LangSmith
  trace (`langsmith_trace_id`) is not deleted: the LangSmith SDK exposes no
  per-run delete API (only whole-project deletion), so trace lifetime is
  governed by LangSmith's own retention config. Tracing is off by default
  (local-first), so nothing leaves the machine unless explicitly enabled.
  Revisit if/when the SDK gains per-run deletion.

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
