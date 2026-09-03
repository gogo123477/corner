"""API request/response shapes. Engine types are reused where they already fit."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.engine.types import DayPlan, Goal, Intensity


class ProfileIn(BaseModel):
    goal: Goal = Goal.MAINTAIN
    weekly_training_target: int = Field(default=3, ge=0, le=7)
    baseline_daily_steps: int = Field(default=7000, ge=0, le=50000)
    day_start: str = Field(default="06:00", pattern=r"^\d{2}:\d{2}$")
    day_end: str = Field(default="22:00", pattern=r"^\d{2}:\d{2}$")
    coaching_tone: str = Field(default="warm", max_length=32)


class ProfileOut(ProfileIn):
    user_id: str
    push_enabled: bool = False


class PushSubscriptionIn(BaseModel):
    """The browser's PushSubscription.toJSON()."""

    endpoint: str = Field(max_length=2000)
    keys: dict[str, str]
    expirationTime: int | None = None  # noqa: N815 (browser field name)


class ActivityIn(BaseModel):
    on: date
    type: str = Field(default="other", max_length=32)
    duration_min: int = Field(ge=0, le=600)
    intensity: Intensity = Intensity.MODERATE
    source: str = Field(default="manual", max_length=32)
    source_ref: str | None = Field(default=None, max_length=255)
    ts: datetime | None = None


class ActivityOut(ActivityIn):
    id: str


class ActivitiesIn(BaseModel):
    activities: list[ActivityIn] = Field(max_length=500)


class RecoveryIn(BaseModel):
    on: date
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    resting_hr_delta_bpm: float | None = Field(default=None, ge=-60, le=60)


class CalendarEventIn(BaseModel):
    start: datetime
    end: datetime
    coarse_type: str = Field(default="meeting", pattern=r"^(meeting|travel|personal|blocked)$")


class CalendarDayIn(BaseModel):
    events: list[CalendarEventIn] = Field(max_length=100)


class BriefOut(BaseModel):
    on: date
    lines: list[str]
    source: str
    status: str
    computed_at: datetime


class PlanOut(BaseModel):
    on: date
    plan: DayPlan
    brief: BriefOut | None
