# ADR 0017: Deployment, hosting and CI/CD

## Status
Accepted

## Context
ADR 0009 referenced a hosting decision that was never recorded. A full product needs an explicit deployment story: where it runs, how it is built and released, how schema migrations are applied, and how to roll back.

## Decision
- **Hosting:** a managed platform (e.g. Railway/Fly.io) runs the app, the worker pool (ADR 0015), and managed PostgreSQL with `pgvector`. Ollama runs on the project's own hardware (ADR 0002), reached over a secured channel.
- **Secrets:** via the platform secret manager (ADR 0009).
- **CI/CD pipeline:** lint → tests (ADR 0019) → offline eval gate (ADR 0012) → build → migrate → deploy.
- **Migrations:** managed with Alembic, applied automatically on deploy, with a documented rollback path.
- **Environments:** at least staging and production, so eval/regression runs against staging before production.

## Alternatives considered
- **Manual deploys** — error-prone and provide no automated quality gate.
- **No migration tool** — schema drifts away from the code; no reproducible upgrade path.
- **A single environment** — no safe place to validate a release before users see it.

## Consequences
- **Easier:** repeatable, gated releases and safe schema evolution.
- **Harder:** the pipeline and multi-environment setup must be built and maintained.
- Replaces the previously dangling "hosting ADR" reference and connects to ADR 0009 (secrets), ADR 0012 (eval gate), and ADR 0019 (tests).
