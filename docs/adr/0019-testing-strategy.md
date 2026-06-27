# ADR 0019: Testing strategy and source-plugin contract tests

## Status
Accepted

## Context
The system spans external APIs, LLM calls, and a multi-stage graph. Without a deliberate test strategy, schema drift (ADR 0010) and routing/eval regressions reach production. A production-grade product treats tests as a first-class concern, not an afterthought.

## Decision
- **Unit tests** for pure logic: routing decisions (ADR 0002), dedup hashing (ADR 0003), schema validators (ADR 0010).
- **Contract tests per source plugin** (ADR 0004): validate live or recorded responses against the expected schema in CI, catching source drift *before* deploy rather than at runtime.
- **Integration tests** for the LangGraph pipeline using recorded fixtures and a stubbed or local model.
- **Eval tests** wired to the offline harness (ADR 0012) as a release gate.
- **Deterministic LLM tests** via pinned versions and recorded responses (ADR 0011) to avoid flakiness and cost.

## Alternatives considered
- **Manual testing** — not repeatable and misses schema drift until it breaks production.
- **Only post-deploy live eval** — regressions have already shipped by the time they are seen.

## Consequences
- **Easier:** drift and regressions are caught pre-deploy, enabling confident refactoring.
- **Harder:** fixtures and recorded responses must be maintained as sources and prompts evolve.
- Connects to ADR 0004 (plugins), ADR 0010 (drift), ADR 0011 (determinism), and ADR 0012 (eval gate); runs inside ADR 0017 (CI/CD).
