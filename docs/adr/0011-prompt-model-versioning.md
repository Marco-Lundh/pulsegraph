# ADR 0011: Prompt and model versioning for reproducibility

## Status
Accepted

## Context
The data model records only which model *class* produced an analysis (local vs. cloud, ADR 0002). Without the exact prompt and model version, a result cannot be reproduced, an eval regression cannot be traced to its cause, and prompt changes cannot be A/B tested. In an LLM system the prompt is part of the executable logic and must be versioned like code.

## Decision
- Prompts live in a versioned registry (`prompts` table): `name`, `role` (analyzer/evaluator/…), `version`, `template`, with one active version per name. Editing a prompt creates a new version row; rows are never mutated in place.
- Every `analyses` row records the `prompt_id` used, the `model_used` class, the pinned `model_version` (e.g. `claude-opus-4-8` or the exact Ollama model digest), and the `params` (temperature, top_p, seed) as JSON.
- The cloud model is always pinned to an explicit version, never a floating alias that the provider can change underneath us.

## Alternatives considered
- **Prompts inline in code** — no runtime A/B, and correlating an eval result with the prompt that produced it requires git archaeology against deploy timestamps.
- **Floating model alias** (e.g. "latest") — non-reproducible; a silent provider update can shift behaviour with no record of what changed.

## Consequences
- **Easier:** results are reproducible, A/B testable, and eval regressions can be attributed to a specific prompt/model version (see ADR 0012).
- **Harder:** requires registry plumbing and a discipline of deliberately bumping and pinning versions.
- Directly supports ADR 0006/0012 (eval attribution) and complements ADR 0002 (which already logs the model class per item).
