"""Compose engine + orchestrator + DB into the one operation the API and the job share."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.engine import plan_day
from app.engine.types import (
    Activity,
    CalendarEvent,
    DayInputs,
    Profile,
    RecoverySignals,
)
from app.orchestrator import render_brief

LOOKBACK_DAYS = 14


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def load_inputs(db: Session, user: models.User, on: date) -> DayInputs:
    prof = db.get(models.Profile, user.id)
    profile = Profile(
        goal=prof.goal if prof else "maintain",
        weekly_training_target=prof.weekly_training_target if prof else 3,
        baseline_daily_steps=prof.baseline_daily_steps if prof else 7000,
        day_start=_parse_time(prof.day_start) if prof else time(6, 0),
        day_end=_parse_time(prof.day_end) if prof else time(22, 0),
        coaching_tone=prof.coaching_tone if prof else "warm",
    )
    since = on - timedelta(days=LOOKBACK_DAYS)
    rows = db.scalars(
        select(models.Activity).where(
            models.Activity.user_id == user.id,
            models.Activity.on_date >= since,
            models.Activity.on_date <= on,
        )
    ).all()
    activities = [
        Activity(on=r.on_date, type=r.type, duration_min=r.duration_min, intensity=r.intensity)
        for r in rows
    ]
    events = db.scalars(
        select(models.CalEvent).where(
            models.CalEvent.user_id == user.id, models.CalEvent.on_date == on
        )
    ).all()
    calendar = [
        CalendarEvent(start=_naive(e.start), end=_naive(e.end), coarse_type=e.coarse_type)
        for e in events
    ]
    rec = db.scalar(
        select(models.RecoveryDay).where(
            models.RecoveryDay.user_id == user.id, models.RecoveryDay.on_date == on
        )
    )
    recovery = RecoverySignals(
        sleep_hours=rec.sleep_hours if rec else None,
        resting_hr_delta_bpm=rec.resting_hr_delta_bpm if rec else None,
    )
    return DayInputs(
        on=on, profile=profile, activities=activities, calendar=calendar, recovery=recovery
    )


def _naive(dt: datetime) -> datetime:
    """Calendar events are stored as the user's local wall-clock time; SQLite drops tzinfo,
    Postgres keeps it. The engine compares within one day, so strip tz consistently."""
    return dt.replace(tzinfo=None)


def compute_day(db: Session, user: models.User, on: date) -> models.Day:
    """(Re)compute the plan and brief for a user-day and persist it. Idempotent."""
    inputs = load_inputs(db, user, on)
    plan = plan_day(inputs)
    brief = render_brief(plan, tone=inputs.profile.coaching_tone, model=get_settings().brief_model)

    day = db.scalar(
        select(models.Day).where(models.Day.user_id == user.id, models.Day.on_date == on)
    )
    if day is None:
        day = models.Day(user_id=user.id, on_date=on)
        db.add(day)
    day.plan_json = plan.model_dump(mode="json")
    day.ledger_json = plan.ledger
    day.brief_json = brief.model_dump(mode="json")
    day.computed_at = datetime.now(tz=None)
    if day.status == "done":
        day.status = "planned"
    db.flush()

    # replace the recommendation rows for the day
    for row in db.scalars(
        select(models.RecommendationRow).where(models.RecommendationRow.day_id == day.id)
    ).all():
        db.delete(row)
    for rec in (plan.training, plan.food, plan.movement):
        db.add(
            models.RecommendationRow(
                day_id=day.id,
                domain=rec.domain.value,
                value=rec.value,
                reason_codes_json=[c.value for c in rec.reasons + rec.rails_applied],
            )
        )
    db.commit()
    return day
