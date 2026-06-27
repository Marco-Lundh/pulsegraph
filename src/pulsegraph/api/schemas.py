"""Pydantic request/response schemas for the REST API."""

import datetime
import uuid

from pydantic import BaseModel, EmailStr, field_validator

from pulsegraph.domain.enums import (
    NotificationChannel,
    NotificationFrequency,
    NotificationStatus,
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
    started_at: datetime.datetime
    finished_at: datetime.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    analysis_id: uuid.UUID
    channel: NotificationChannel
    dedup_key: str
    status: NotificationStatus
    delivered_at: datetime.datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin: review queue
# ---------------------------------------------------------------------------


class ReviewDecisionCreate(BaseModel):
    decision: ReviewDecision
    corrected_label: str | None = None
    note: str | None = None


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
# Admin: notification settings
# ---------------------------------------------------------------------------


class NotificationSettingOut(BaseModel):
    user_id: uuid.UUID
    channel: NotificationChannel
    frequency: NotificationFrequency
    destination: str | None
    is_active: bool

    model_config = {"from_attributes": True}
