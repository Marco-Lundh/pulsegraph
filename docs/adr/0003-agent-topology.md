# ADR 0003: Agent topology — six-stage pipeline

## Status
Accepted

## Context
The system should be a realistic, multi-stage agent pipeline with clear separation of concerns, not a monolithic "one agent does everything" solution. This is central to the production pattern: each stage must be able to fail, retry, and be traced independently of the others.

## Decision
The pipeline is built as six distinct agent roles in a LangGraph graph:

```
Watcher → Fetcher → Embedder → Analyzer → Evaluator → Notifier
```

- **Watcher** — keeps track of each user's active watches (defined via the frontend prompt) and triggers the Fetcher periodically per watch.
- **Fetcher** — retrieves raw data from an external source (JobTech/Riksdagen/ENTSO-E). Source-agnostic via a plugin pattern (see ADR 0004). Handles retries, timeouts, circuit breaker.
- **Embedder** — vectorizes new content and deduplicates against content previously seen per user.
- **Analyzer** — core reasoning via hybrid model routing (see ADR 0002).
- **Evaluator** — a dedicated agent that assesses the relevance and confidence of the Analyzer output before it proceeds to the user. Low confidence → flagged for review instead of auto-notifying.
- **Notifier** — formats and delivers results to the dashboard/alert.

Each transition between agents is an explicit LangGraph edge with its own state, which makes every step individually checkpointable and traceable.

## Alternatives considered
- **A simpler 3-stage pipeline** (Fetch → Process → Notify) — faster to build, but hides the granularity needed to surface error handling and eval as separate, observable steps.
- **A monolithic agent with internal logic** — easiest to implement but makes it impossible to isolate failures the way a production pattern requires, because a fault in one sub-step cannot be isolated or traced separately.

## Consequences
- **Easier:** each agent role can be tested, debugged, and evaluated in isolation; faults can be isolated to the step where they occur.
- **Harder:** more infrastructure and state management than a simpler pipeline; requires a clear definition of what is passed between each step.
- The Evaluator as its own step (rather than baked into the Analyzer) is a deliberate choice to make eval a first-class, visible part of the architecture (see ADR 0006).
