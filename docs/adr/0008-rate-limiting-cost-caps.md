# ADR 0008: Rate limiting and cost caps per user

## Status
Accepted

## Context
With real multi-tenant authentication (ADR 0005) and a hybrid model routing that includes a paid cloud model (ADR 0002), there is a concrete risk: one or more users creating many watches could drive cost far above the budget (~5–10 USD/month) or get the system rate-limited by external APIs (JobTech, Riksdagen, ENTSO-E).

## Decision
Hard limits are implemented per `user_id`:
- A maximum number of concurrently active watches per user.
- A maximum number of agent pipeline runs per hour per user.
- Global cost monitoring for cloud-model calls (Claude API), with a warning/pause when a threshold approaches the configured budget.

The limits are configurable values, not hardcoded magic numbers, so they can be adjusted without code changes once actual usage becomes clear.

## Alternatives considered
- **No limits, relying on low actual traffic** — risky given that the system is designed to scale to more users; a single abusive user (intentionally or not) could consume the entire budget or trigger external rate limits that affect all users.
- **A global limit instead of per-user** — simpler to implement but unfair (one user can block everyone else) and gives no signal about who is causing the load.

## Consequences
- **Easier:** predictable cost and resource usage; concrete, cost-aware system design.
- **Harder:** requires a mechanism to count and reset usage per user (e.g. a simple counter with a time window), plus clear UX for what happens when a user hits their limit (should the watch be paused, or the next run queued to the next window?).
- Links to ADR 0007 (observability): limit violations should be visible in the logs/tracing, not silently swallowed.
- The counter mechanism is implemented via Redis atomic `INCR`/`EXPIRE` — see ADR 0022.
