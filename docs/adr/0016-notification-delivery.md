# ADR 0016: Notification delivery channels and digest batching

## Status
Accepted

## Context
The Notifier currently targets only the dashboard (ADR 0003). For a watch product the core value is timely delivery, so it needs real channels (email, webhook, push) plus controls that prevent alert fatigue and duplicate alerts.

## Decision
- Multiple delivery channels behind a channel interface (dashboard, email, webhook), selectable per user via `notification_settings` (channel + frequency: instant or daily digest + destination).
- **Digest batching:** lower-urgency results can be batched into a periodic digest instead of one message per item.
- **Alert dedup:** a `dedup_key` (per user + item) prevents the same result from being delivered twice, reusing the dedup identity established by the Embedder (ADR 0003).
- Delivery is tracked per notification (channel, status, delivered_at) and retried on transient failure.

## Alternatives considered
- **Dashboard only** — not a real notification product; the user must come looking.
- **One message per item, no batching** — alert fatigue; users disable notifications entirely.
- **No dedup** — duplicate alerts erode trust in the product.

## Consequences
- **Easier:** a complete delivery story with fatigue and duplicate controls built in.
- **Harder:** per-channel integrations and digest scheduling to build and operate.
- Connects to ADR 0003 (Notifier and dedup identity) and ADR 0015 (digest scheduling runs on the same scheduler).
