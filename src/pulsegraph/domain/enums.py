"""Enumerations shared across the system.

These mirror the PostgreSQL enum types declared in the data model
(see docs/data-model.md). Keeping them in one place ensures the
application layer and the database agree on the allowed values.
"""

from enum import StrEnum


class SourceKind(StrEnum):
    """An open data source the system can watch (ADR 0004)."""

    JOBTECH = "jobtech"
    RIKSDAGEN = "riksdagen"
    ENTSOE = "entsoe"


class SourceStatus(StrEnum):
    """Drift state of a source (ADR 0010)."""

    HEALTHY = "healthy"
    PAUSED = "paused"


class RunStatus(StrEnum):
    """Lifecycle of a single pipeline run (ADR 0015)."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PAUSED = "paused"


class ModelKind(StrEnum):
    """Which model class produced an output (ADR 0002)."""

    OLLAMA = "ollama"
    CLAUDE = "claude"


class EvalStatus(StrEnum):
    """Verdict of the Evaluator on an analysis (ADR 0006)."""

    APPROVED = "approved"
    REVIEW = "review"


class NotificationStatus(StrEnum):
    """Delivery state of a notification (ADR 0016)."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class UserRole(StrEnum):
    """Authorization role of a user (ADR 0021)."""

    USER = "user"
    ADMIN = "admin"


class PromptRole(StrEnum):
    """Which agent a prompt belongs to (ADR 0011)."""

    ANALYZER = "analyzer"
    EVALUATOR = "evaluator"


class ReviewDecision(StrEnum):
    """A human verdict from the review queue (ADR 0012)."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class NotificationChannel(StrEnum):
    """A delivery channel for notifications (ADR 0016)."""

    DASHBOARD = "dashboard"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationFrequency(StrEnum):
    """How often a channel delivers (ADR 0016)."""

    INSTANT = "instant"
    DAILY_DIGEST = "daily_digest"
