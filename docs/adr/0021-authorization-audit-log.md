# ADR 0021: Authorization, roles and audit logging

## Status
Accepted

## Context
The architecture emphasizes audit trails, but only pipeline runs are recorded (ADR 0007) — user and account actions are not. There is also no role model, yet some surfaces (system health, the review queue, other tenants' data, limit configuration) must be operator-only.

## Decision
- **Role-based authorization** on top of authentication (ADR 0005): at least `user` and `admin`. Admin-only surfaces include the operational/system-health dashboards (ADR 0020), the cross-tenant review queue (ADR 0006/0012), and limit configuration (ADR 0008).
- **Tenant isolation** is enforced in every query by `user_id` scoping (ADR 0005) and covered by tests (ADR 0019).
- **Audit log:** an `audit_log` records security-relevant user/account actions (login, watch create/update/delete, role changes, data export/deletion) with actor, action, entity, and timestamp.
- **Auth endpoints** are themselves rate-limited (ADR 0008) to resist brute force.

## Alternatives considered
- **A single role** — operators and users share surfaces, a privacy and security risk (one user could see another's data or system internals).
- **No audit log** — no forensic trail, which directly contradicts the system's audit-trail goal.

## Consequences
- **Easier:** enforceable least privilege and a forensic trail for security-relevant actions.
- **Harder:** role checks across every surface and keeping audit coverage complete as features are added.
- Connects to ADR 0005 (auth/scoping), ADR 0008 (limits), ADR 0019 (isolation tests), and ADR 0020 (admin surfaces).
