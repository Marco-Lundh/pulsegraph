# ADR 0007: Observability via LangSmith tracing

## Status
Accepted

## Context
Eval (ADR 0006) gives insight into output quality, but not into the *execution* of the pipeline. If a user's watch repeatedly produces incorrect results, or if an agent starts responding abnormally slowly, we need a way to see exactly where in the chain it happens — otherwise "checkpoints and rollback" are merely theoretical concepts without a concrete tool to actually use them.

## Decision
The entire LangGraph execution is instrumented with **LangSmith** (free tier), which provides:
- A trace per pipeline run: which agent ran, for how long, with which input/output, and the state at each step.
- The ability to do "time travel" debugging — step back to an earlier checkpoint and see exactly what happened.
- A direct link between an error visible in the dashboard and the underlying execution that caused it.

## Alternatives considered
- **A custom logging solution (e.g. structured logs to a database)** — entirely feasible and cheaper in conceptual complexity, but requires building the visualization/search ourselves. LangSmith provides this out of the box and is built specifically for LangGraph, which is a stronger "right tool for the right framework" signal.
- **No structured observability, just print/console logs** — insufficient to meet the explicit requirement for traceability and rollback points.

## Consequences
- **Easier:** provides immediate, visual traceability without building our own tooling; delivers genuine production maturity — the ability to debug the agent system in operation, not just to build it.
- **Harder:** introduces an external dependency (the LangSmith service); the free tier has limits that must be respected given the multi-tenant scale (links to ADR 0008, rate limiting).
