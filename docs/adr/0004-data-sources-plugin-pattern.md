# ADR 0004: Data sources — source-agnostic plugin pattern

## Status
Accepted

## Context
The system should be able to watch continuously updated, open data. The goal is not to support "every open source that exists" in an MVP (an unrealistic scope), but to prove that the architecture *can* be extended to more sources without a rewrite.

## Decision
The MVP supports three open, free Swedish/European data sources with different data characteristics:

1. **JobTech (Arbetsförmedlingen)** — job ads, text-based, updated continuously. The core of the product's primary use case (a user watching relevant job ads).
2. **Riksdagen open data** — motions and votes, text + structured metadata. Proves that the Fetcher handles a different data structure than JobTech.
3. **ENTSO-E** — electricity-price data, a numeric time series updated hourly. Proves that the pipeline handles an entirely different data type (time series, not free text).

The Fetcher agent is implemented with a **plugin pattern**: each source is a separate module that implements a shared interface (fetch, parse, validate-schema). Adding a fourth source is a matter of configuration, not a rewrite of the Fetcher core.

## Alternatives considered
- **A single source (JobTech only)** — faster to finish, but does not prove source-agnostic design, which was an explicit requirement.
- **Unlimited number of sources ("every open source that exists")** — an unrealistic scope for an MVP; no clear delivery point.
- **Hardcoded logic per source without a shared interface** — faster initially, but each new source would require changes to the Fetcher core, which breaks the source-agnostic requirement.

## Consequences
- **Easier:** adding new sources in the future; clear extensibility without rewriting the Fetcher core.
- **Harder:** requires designing a sufficiently general interface from the start that works for free text, structured metadata, and time-series data alike.
- Directly connected to ADR 0010 (schema validation): each source's plugin must validate its own response schema before data proceeds through the pipeline.
