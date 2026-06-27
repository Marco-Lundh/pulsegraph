# ADR 0010: Schema validation and handling of source drift

## Status
Accepted

## Context
External APIs (JobTech, Riksdagen, ENTSO-E) can change their response schema over time — fields are renamed, new fields appear, data types change. This is one of the most common causes of silent production failures in real data pipelines: the code does not crash obviously, but starts processing incorrect or empty data without anyone noticing.

## Decision
Each source's Fetcher plugin (see ADR 0004) validates the incoming response against an expected schema **before** the data is passed on to the Embedder. On a mismatch:
- The pipeline stops explicitly for that run (fail loud, not fail silent).
- A clear warning is logged and appears in the dashboard's source log ("Source schema for X did not match the expected format, run paused").
- The run for that specific source is marked as paused until the schema either returns to the expected format or the plugin code is updated manually.
- Other sources and other users' watches are unaffected by a single source drifting.

## Alternatives considered
- **No validation, trusting that fields exist** — risk of silent failures that are much harder to detect and debug; code crashes unpredictably further down the pipeline instead of clearly at the source.
- **Attempting to automatically "heal" deviating data (e.g. fallback values for missing fields)** — hides the problem rather than surfacing it; can give the user incorrect results without warning. Rejected because transparency is prioritized over uptime for a single source.

## Consequences
- **Easier:** failures are detected early and clearly, isolated to the affected source; addresses a concrete, real production problem (silent data failures on source drift).
- **Harder:** requires defining and maintaining an explicit schema per source, plus deciding what "deviating enough to stop" means in practice (e.g. a new optional field should not stop the pipeline, but a dropped required field should).
- Directly connected to ADR 0007 (observability) — schema deviations should be clearly visible in the tracing, not just in a single log line.
