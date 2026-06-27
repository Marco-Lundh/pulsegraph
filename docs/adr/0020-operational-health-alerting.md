# ADR 0020: Operational health checks and alerting

## Status
Accepted

## Context
The system-health metric (ADR 0006) measures output *quality*, not infrastructure liveness. Operators also need to know whether the worker is alive, the queue is draining, Ollama is reachable, the database is up, and external sources are responding — and to be alerted when they are not. These are distinct concerns and must not be conflated.

## Decision
- **Health/readiness endpoints** for the app and the worker (database connectivity, queue connectivity, Ollama reachability).
- **Operational metrics** distinct from product eval health: queue depth, job latency, worker liveness, external-API error rates, and cloud-model spend versus the cap (ADR 0008).
- **Alerting** on operator-facing thresholds — worker down, queue backlog, spend nearing the cap, repeated source pauses (ADR 0010) — routed to an operator channel.
- Operational signals correlate with LangSmith traces (ADR 0007) for root-cause analysis.

## Alternatives considered
- **Rely on the product health metric only** — blind to infrastructure failures; a dead worker shows as "no new results," not as an alert.
- **No alerting** — failures are discovered by users rather than operators.

## Consequences
- **Easier:** operational failures are detected proactively, before users notice.
- **Harder:** metrics and alerting plumbing to build, plus threshold tuning.
- Connects to ADR 0006 (product health, the complementary view), ADR 0007 (tracing), ADR 0008 (spend), and ADR 0015 (queue).
