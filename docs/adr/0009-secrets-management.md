# ADR 0009: Secrets management

## Status
Accepted

## Context
The system uses several external API keys (Claude API, possibly JobTech/Riksdagen/ENTSO-E if they require keys, LangSmith). These must under no circumstances end up in version control or be exposed in client code, for security reasons.

## Decision
- All secrets are handled via environment variables, read from a `.env` file locally (never committed — `.gitignore` includes `.env` from the start).
- In production (hosting), secrets are handled via the host platform's built-in secret manager (e.g. Railway/Fly.io environment variables), not files on disk.
- A `.env.example` file is checked in with all required variable names (without actual values) so that other developers know what is needed to run the project.

## Alternatives considered
- **Secrets directly in code or in committed configuration files** — ruled out immediately; a fundamental security flaw.
- **A full-scale secrets service (e.g. HashiCorp Vault)** — overkill for a project of this scale and budget; the host platform's built-in solution is sufficient.

## Consequences
- **Easier:** standard practice that is trivial to implement correctly from the start; an obvious line in the README under security considerations.
- **Harder:** no significant drawbacks — this is a zero-cost best practice.
