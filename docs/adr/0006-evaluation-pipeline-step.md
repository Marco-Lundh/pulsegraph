# ADR 0006: Eval as its own pipeline step with an aggregated health metric

## Status
Accepted

## Context
"Eval" is often in demand but is rarely implemented visibly in production systems. We want eval to be part of the production flow, not a separate, decoupled offline script.

## Decision
A dedicated **Evaluator agent** runs after the Analyzer for every piece of data processed:
- Assesses the relevance and confidence of the Analyzer output.
- Results are logged per item (visible in the dashboard's source list, with source + timestamp).
- Results are also aggregated into a **system-health metric** shown directly in the dashboard (e.g. "94% of analyses approved in the last 24h").
- Low-confidence results go to a review queue instead of automatically notifying the user (human-in-the-loop pattern).

## Alternatives considered
- **Eval as a separate offline script/CI step** — more common in real production systems for regression-testing model quality over time, but invisible in the running system. Rejected as the *only* eval mechanism because it does not provide the visible quality control in operation that we want.
- **No separate eval step, quality control baked into the Analyzer** — simpler but opaque; makes it impossible to surface eval as a distinct, reviewable part of the architecture.

## Consequences
- **Easier:** gives a clear, visual signal that the system does not blindly trust itself; a natural link to hybrid model routing (ADR 0002) — low confidence can also trigger re-routing to the cloud model.
- **Harder:** requires defining what "relevance" and "confidence" concretely mean per source type (a job ad vs. a parliamentary motion vs. electricity-price data have different evaluation criteria).
- Noted in the README that a more extensive offline eval / regression test (CI step) is a natural future extension but not part of this MVP.
