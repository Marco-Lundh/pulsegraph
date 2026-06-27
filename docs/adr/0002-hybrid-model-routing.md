# ADR 0002: Hybrid model routing — local model + cloud-model fallback

## Status
Accepted

## Context
The budget for LLM calls is limited (~5–10 USD/month total for the project). The system needs to handle continuous analysis of incoming data (job ads, parliamentary motions, electricity-price data) for potentially several users at once. Sending every query to a paid cloud model would scale poorly as users and watches grow.

## Decision
The Analyzer agent routes each task based on complexity:
- **Simple/high-volume tasks** (classification, simple extraction, formatting) → local model via **Ollama** (e.g. Llama 3.1 8B or Mistral), free, running on our own hardware.
- **Complex/critical tasks** (nuanced relevance assessment, summaries shown directly to the user, edge cases where the local model has low confidence) → **Claude API**.
- Fallback logic: if the local model times out or returns a low confidence score, the task is automatically re-routed to the cloud model instead of failing.

## Alternatives considered
- **Cloud model only** — simpler to implement, but scales poorly cost-wise as users/watches grow and does not take advantage of cost-optimized routing.
- **Local model only** — free, but lower quality on complex reasoning, and no protection against high load on the local machine.
- **Static split per agent type** (e.g. "Embedder always local, Analyzer always cloud") — simpler but less realistic; real production systems route dynamically based on actual difficulty and system state, not just agent identity.

## Consequences
- **Easier:** keeps running cost within budget even with several concurrent users; it is an established production pattern (cost-optimized model routing).
- **Harder:** requires clear logic for determining "complexity" and confidence thresholds; introduces an additional source of error (the routing decision itself can be wrong) that must be logged and traceable (see ADR 0007).
- The per-task routing decision is logged in the dashboard's source list ("this analysis was performed by: local/Claude") for transparency.
