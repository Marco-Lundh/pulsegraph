"""Pydantic request/response schemas for the REST API."""

import datetime
import uuid

from pydantic import BaseModel, EmailStr, field_validator

from pulsegraph.domain.enums import (
    EvalStatus,
    ModelKind,
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
    PromptRole,
    ReviewDecision,
    RunStatus,
    SourceKind,
    SourceStatus,
    UserRole,
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Watches  (schedule_interval serialised as seconds)
# ---------------------------------------------------------------------------


class WatchCreate(BaseModel):
    source: SourceKind
    prompt: str
    config: dict = {}
    schedule_interval_seconds: int = 3600

    @field_validator("schedule_interval_seconds")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 60:
            raise ValueError("schedule_interval_seconds must be >= 60")
        return v


class WatchUpdate(BaseModel):
    prompt: str | None = None
    config: dict | None = None
    is_active: bool | None = None
    schedule_interval_seconds: int | None = None

    @field_validator("schedule_interval_seconds")
    @classmethod
    def _positive(cls, v: int | None) -> int | None:
        if v is not None and v < 60:
            raise ValueError("schedule_interval_seconds must be >= 60")
        return v


class WatchOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    source: SourceKind
    prompt: str
    config: dict
    is_active: bool
    schedule_interval_seconds: int
    last_run_at: datetime.datetime | None
    next_run_at: datetime.datetime
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: object) -> "WatchOut":
        d = {
            c: getattr(obj, c)
            for c in (
                "id",
                "user_id",
                "source",
                "prompt",
                "config",
                "is_active",
                "last_run_at",
                "next_run_at",
                "created_at",
                "updated_at",
            )
        }
        d["schedule_interval_seconds"] = int(
            obj.schedule_interval.total_seconds()  # type: ignore[union-attr]
        )
        return cls(**d)


# ---------------------------------------------------------------------------
# Pipeline runs
# ---------------------------------------------------------------------------


class RunOut(BaseModel):
    id: uuid.UUID
    watch_id: uuid.UUID
    status: RunStatus
    error: str | None
    # The LangSmith root trace id (ADR 0007), surfaced so the dashboard can
    # link a run — especially a failed one — back to its execution trace.
    # None when tracing was disabled for the run (local-first default).
    langsmith_trace_id: str | None
    started_at: datetime.datetime
    finished_at: datetime.datetime | None

    model_config = {"from_attributes": True}


class ItemResultOut(BaseModel):
    """One analyzed item in a run, with its analysis and evaluation.

    Closes two backend/UI parity gaps: which model analyzed the item
    (``model_used``/``model_version``, ADR 0002) and how the Evaluator
    graded it (``relevance_score``/``eval_confidence``/``eval_status``,
    ADR 0006) — neither was ever exposed to end users. ``notified`` says
    whether the item produced a dashboard notification this run.

    Evaluation fields are optional so an analysis awaiting its grade still
    renders; every persisted item always carries exactly one analysis.
    """

    item_id: uuid.UUID
    external_id: str | None
    source: SourceKind
    fetched_at: datetime.datetime
    model_used: ModelKind
    model_version: str
    summary: str
    analysis_confidence: float
    relevance_score: float | None
    eval_confidence: float | None
    eval_status: EvalStatus | None
    notified: bool


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class DeliveryOut(BaseModel):
    """One sibling channel's delivery status for a notification (ADR 0016).

    The dashboard feed shows one row per item (the dashboard channel); each
    row carries the per-channel delivery status of the email/webhook sends
    for the same item so the user can see whether each channel got through.
    """

    channel: NotificationChannel
    status: NotificationStatus
    delivered_at: datetime.datetime | None
    attempts: int

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    analysis_id: uuid.UUID
    channel: NotificationChannel
    dedup_key: str
    status: NotificationStatus
    delivered_at: datetime.datetime | None
    deliveries: list[DeliveryOut] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin: review queue
# ---------------------------------------------------------------------------


class ReviewDecisionCreate(BaseModel):
    decision: ReviewDecision
    corrected_label: str | None = None
    note: str | None = None


# ---------------------------------------------------------------------------
# Admin: prompt registry (ADR 0011)
# ---------------------------------------------------------------------------


class PromptOut(BaseModel):
    id: uuid.UUID
    name: str
    role: PromptRole
    version: int
    template: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class PromptCreate(BaseModel):
    """Create a new version of an existing prompt (ADR 0011).

    The ``role`` is derived from the existing versions of ``name`` and the
    ``version`` is auto-incremented, so a new family can't accidentally
    create a second active prompt for the same role. ``activate`` makes the
    new version the one the pipeline loads at runtime.
    """

    name: str
    template: str
    activate: bool = True

    @field_validator("template")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        # A blank template is truthy enough to override the client's default
        # and would run as an empty system prompt; reject it server-side, not
        # only in the dashboard form.
        if not v.strip():
            raise ValueError("template must not be empty")
        return v


# ---------------------------------------------------------------------------
# Admin: source health
# ---------------------------------------------------------------------------


class SourceHealthOut(BaseModel):
    source: SourceKind
    status: SourceStatus
    drift_detail: str | None
    last_checked_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Notification settings (per-user channel preferences)
# ---------------------------------------------------------------------------


class NotificationSettingOut(BaseModel):
    user_id: uuid.UUID
    channel: NotificationChannel
    frequency: NotificationFrequency
    destination: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class NotificationSettingUpdate(BaseModel):
    frequency: NotificationFrequency = NotificationFrequency.INSTANT
    destination: str | None = None
    is_active: bool = True
