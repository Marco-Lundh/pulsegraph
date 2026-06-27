# PulseGraph

A multi-tenant agent-orchestration system that continuously watches open data
sources on behalf of each user, analyzes new content with a cost-aware hybrid of
local and cloud models, evaluates the quality of every analysis, and notifies
the user — instrumented end to end for traceability.

The design is documented as Architecture Decision Records in
[`docs/adr/`](docs/adr/), with the system architecture in
[`docs/architecture.md`](docs/architecture.md) and the data model in
[`docs/data-model.md`](docs/data-model.md).

## Pipeline

```
Watcher → Fetcher → Embedder → Analyzer → Evaluator → Notifier
```

Built on LangGraph (ADR 0001), with hybrid local/cloud model routing (ADR 0002),
a source-agnostic plugin pattern (ADR 0004), and eval as a first-class pipeline
step (ADR 0006).

## Running locally

PulseGraph is **local-first**: the default configuration runs the entire system
on your machine with no cloud dependencies and no API keys.

Requirements: Python 3.12+, [uv](https://github.com/astral-sh/uv), Docker, and
[Ollama](https://ollama.com) for the local model.

```bash
# 1. Start Postgres (pgvector) and Redis
docker compose up -d

# 2. Configure (the defaults are fully local)
cp .env.example .env

# 3. Install dependencies
uv sync --extra dev

# 4. Run the tests
uv run pytest
```

The cloud model (Claude) and LangSmith tracing are opt-in via `.env`
(`USE_CLOUD_MODEL`, `LANGSMITH_ENABLED`); with the defaults the system never
leaves your machine except to fetch from the open data sources.

## Project layout

```
pulsegraph/
  config.py          Settings and local-first toggles
  domain/            Enumerations and shared types
  db/                SQLAlchemy models (the data model)
  sources/           Source-agnostic Fetcher plugins (ADR 0004)
  pipeline/          Core pipeline logic (dedup, routing, ...)
docs/                ADRs, architecture, and data model
```

Tests are colocated next to the code they cover as `<module>_test.py`.
