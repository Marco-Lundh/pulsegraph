# ADR 0015: Scheduling, task queue and idempotent workers

## Status
Accepted

## Context
The Watcher "triggers the Fetcher periodically" (ADR 0003), but the system-level execution mechanism is unspecified. A continuous, multi-tenant product needs explicit scheduling, a queue, a worker pool, system-level retry/backoff (distinct from the in-graph retries of the Fetcher), and idempotency so a watch is never processed twice concurrently.

## Decision
- A scheduler enqueues a job per due watch onto a task queue (e.g. a Redis-backed Arq/Celery); a pool of workers consumes jobs and runs the LangGraph pipeline.
- **Idempotency:** at most one in-flight run per watch, enforced by a partial unique index on `pipeline_runs(watch_id) WHERE status = 'running'`, plus a claim/lease on dequeue.
- Scheduling state lives on the watch (`schedule_interval`, `last_run_at`, `next_run_at`); the scheduler selects watches where `next_run_at <= now` and the source is healthy (ADR 0010).
- System-level retry with backoff for transient failures; permanent failures surface in observability (ADR 0007) and pause the watch.
- Per-user run rate limits (ADR 0008) are enforced at enqueue time.

## Alternatives considered
- **An in-process loop or bare cron without a queue** — no backpressure, no horizontal scaling, and in-flight work is lost on restart.
- **Fire-and-forget triggering** — no idempotency, leading to duplicate runs and double cost.

## Consequences
- **Easier:** horizontally scalable, crash-safe, with no duplicate runs.
- **Harder:** introduces queue infrastructure and worker operations to run and monitor (ADR 0020).
- Connects to ADR 0003 (Watcher), ADR 0008 (rate limits), ADR 0010 (health gate), and ADR 0007 (failure visibility).
