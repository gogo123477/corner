"""Core tables (design doc §5). JSON columns hold engine/plan blobs.

Sensitive health-derived fields are marked with `info={"sensitive": True}` so an
export/analytics path can exclude them. Column-level encryption is a Phase 1 item.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    auth_ref: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped[Profile | None] = relationship(back_populates="user", uselist=False)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    goal: Mapped[str] = mapped_column(String(32), default="maintain")
    weekly_training_target: Mapped[int] = mapped_column(Integer, default=3)
    baseline_daily_steps: Mapped[int] = mapped_column(Integer, default=7000)
    day_start: Mapped[str] = mapped_column(String(5), default="06:00")
    day_end: Mapped[str] = mapped_column(String(5), default="22:00")
    coaching_tone: Mapped[str] = mapped_column(String(32), default="warm")
    constraints_json: Mapped[dict] = mapped_column(JSON, default=dict, info={"sensitive": True})
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="profile")


class Day(Base):
    __tablename__ = "days"
    __table_args__ = (UniqueConstraint("user_id", "on_date", name="uq_day_user_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date)
    ledger_json: Mapped[dict] = mapped_column(JSON, default=dict, info={"sensitive": True})
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    brief_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="planned")  # planned | opened | done
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date, index=True)
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    type: Mapped[str] = mapped_column(String(32), default="other")
    source: Mapped[str] = mapped_column(
        String(32), default="manual"
    )  # healthkit | health_connect | manual
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)  # dedupe key
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    intensity: Mapped[str] = mapped_column(String(16), default="moderate")
    load_metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, info={"sensitive": True})


class RecoveryDay(Base):
    """Per-day recovery signals (sleep, resting HR) — derived, never raw samples."""

    __tablename__ = "recovery_days"
    __table_args__ = (UniqueConstraint("user_id", "on_date", name="uq_recovery_user_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date)
    sleep_hours: Mapped[float | None] = mapped_column(
        Float, nullable=True, info={"sensitive": True}
    )
    resting_hr_delta_bpm: Mapped[float | None] = mapped_column(
        Float, nullable=True, info={"sensitive": True}
    )


class CalEvent(Base):
    __tablename__ = "cal_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    on_date: Mapped[date] = mapped_column(Date, index=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    coarse_type: Mapped[str] = mapped_column(String(16), default="meeting")
    # deliberately no title / attendees / location: raw calendar is not persisted


class Meal(Base):
    """Phase 1. Present now so the contract is fixed; no photo is ever stored."""

    __tablename__ = "meals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    input_type: Mapped[str] = mapped_column(String(16))  # photo | voice | text
    estimate_json: Mapped[dict] = mapped_column(JSON, default=dict, info={"sensitive": True})
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    day_id: Mapped[str] = mapped_column(ForeignKey("days.id"), index=True)
    domain: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(String(32))
    reason_codes_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(16), default="proposed"
    )  # proposed | accepted | overridden


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    rec_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))  # accepted | overridden | ignored
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CoachingProfile(Base):
    """Phase 2 (the B bet). Starts empty and learns which nudges work."""

    __tablename__ = "coaching_profile"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tone_weights_json: Mapped[dict] = mapped_column(JSON, default=dict)
    learned_signals_json: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
