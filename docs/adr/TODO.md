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

- **LangSmith traces are not purged on erasure/retention (ADR 0018).**
  Consent at signup is now recorded, but a purged run's external LangSmith
  trace (`langsmith_trace_id`) is not deleted: the LangSmith SDK exposes no
  per-run delete API (only whole-project deletion), so trace lifetime is
  governed by LangSmith's own retention config. Tracing is off by default
  (local-first), so nothing leaves the machine unless explicitly enabled.
  Revisit if/when the SDK gains per-run deletion.

  (ADR 0011 — prompt registry — is now closed: the analyzer loads the
  active template from the registry at runtime, and an admin Prompts tab
  edits/versions/activates prompts. ADR 0014 — embedding versioning — is
  also closed: EMBEDDING_DIM is centralized with a dimension guard, a
  re-embed job backfills stale-model vectors, and a model-aware pgvector
  similarity query powers semantic dedup. ADR 0001 — graph checkpointer —
  is closed: a config-selected LangGraph checkpointer (durable Postgres
  backend) persists each run's state for time-travel/rollback.)

## Larger deferred work

- **Offline eval not yet tuned against the real model (ADR 0012).** The
  golden datasets, the CI release gate (`scripts/offline_eval.py`), and the
  review → dataset growth job (`scripts/grow_golden.py`) all run against
  the deterministic offline predictor. Running the harness against the real
  Ollama/Claude routing and empirically tuning `EVAL_MIN_F1` is still open
  (the harness's predictor is already injectable for this).

  (ADR 0017 — deployment/CD — is now closed: a multi-stage `Dockerfile`
  serves the api/worker/migrate roles from one image, `docker-compose.prod.yml`
  reproduces the full stack locally, `.github/workflows/deploy.yml` chains
  after CI to build → migrate → deploy with a staging/production split, and
  Alembic migrations run automatically on deploy with a documented rollback
  path. The actual host rollout is a single platform-agnostic seam
  (`scripts/deploy_release.sh`) an operator wires to their platform, gated so
  the pipeline is a safe no-op until configured. See `docs/deployment.md`.)
