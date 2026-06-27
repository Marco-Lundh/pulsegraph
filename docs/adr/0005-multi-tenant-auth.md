# ADR 0005: Multi-tenant architecture with real authentication

## Status
Accepted

## Context
The system is designed as if it were a real product with multiple users, not a solution built for a single user. Each user should be able to define their own watches (via a free-text prompt in the frontend) that persist across sessions.

## Decision
The system is implemented with real authentication (e.g. email + password or OAuth) and a data model where each watch (`watch`) is linked to a specific user (`user_id`). The Watcher agent iterates over active watches per user, not a global list.

## Alternatives considered
- **Session-based, no login** — simpler to implement, no database for user accounts required. Rejected because it does not represent a realistic product; watches would disappear on page reload, undermining the entire "continuous watching" value proposition.

## Consequences
- **Easier:** represents a real product architecture; gives a clear data-model design (users, watches, items, eval results).
- **Harder:** requires real authentication logic, password handling (or OAuth integration), and ensuring that one user's watches/data are isolated from others' (row-level scoping in the database).
- Direct link to ADR 0008 (rate limiting): limits on the number of watches and agent runs are set per `user_id`, which is only meaningful with real user accounts.
