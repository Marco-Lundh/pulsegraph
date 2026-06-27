# ADR 0018: Data retention and GDPR compliance

## Status
Accepted

## Context
This is a real EU product that stores personal data: user accounts, their watches (which can reveal interests and job-seeking), and fetched content that may itself contain personal data. GDPR obligations apply — lawful basis, retention limits, the right to erasure, and data portability.

## Decision
- **Data minimization:** store only what the pipeline needs; raw payloads are kept only as long as useful, then pruned.
- **Retention policy per table** (e.g. items/analyses/traces expire after a configurable window), enforced by a scheduled cleanup job (running on the scheduler from ADR 0015).
- **Right to erasure:** deleting a user cascades to all their data (modeled via `ON DELETE CASCADE`); a documented deletion flow also covers derived data and external traces (LangSmith, ADR 0007).
- **Right to portability:** a user-data export.
- **Lawful basis and consent** recorded at signup; secrets and PII are never written to traces or logs (ADR 0007/0009).

## Alternatives considered
- **Keep everything forever** — a GDPR violation and an ever-growing risk surface.
- **Ad-hoc deletion** — incomplete; leaves derived data and external traces behind.

## Consequences
- **Easier:** a legally operable EU product with deletion and export as first-class flows.
- **Harder:** retention jobs and export tooling to build, and care to ensure derived/external data is covered.
- Connects to ADR 0005 (user data), ADR 0007 (trace PII), and ADR 0009 (secrets).
