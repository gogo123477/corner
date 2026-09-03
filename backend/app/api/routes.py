from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import current_user
from app.config import get_settings
from app.db import get_db
from app.engine.types import DayPlan
from app.service import compute_day

router = APIRouter(prefix="/v1")


# ---------- profile ----------


@router.get("/profile", response_model=schemas.ProfileOut)
def get_profile(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    prof = db.get(models.Profile, user.id)
    if prof is None:
        return schemas.ProfileOut(user_id=user.id)
    return schemas.ProfileOut(
        user_id=user.id,
        goal=prof.goal,
        weekly_training_target=prof.weekly_training_target,
        baseline_daily_steps=prof.baseline_daily_steps,
        day_start=prof.day_start,
        day_end=prof.day_end,
        coaching_tone=prof.coaching_tone,
        push_enabled=bool((prof.constraints_json or {}).get("push_subscription")),
    )


@router.put("/profile", response_model=schemas.ProfileOut)
def put_profile(
    body: schemas.ProfileIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prof = db.get(models.Profile, user.id) or models.Profile(user_id=user.id)
    prof.goal = body.goal.value
    prof.weekly_training_target = body.weekly_training_target
    prof.baseline_daily_steps = body.baseline_daily_steps
    prof.day_start = body.day_start
    prof.day_end = body.day_end
    prof.coaching_tone = body.coaching_tone
    db.add(prof)
    db.commit()
    return get_profile(user, db)


# ---------- push ----------


@router.get("/push/vapid-public-key")
def vapid_public_key():
    return {"key": get_settings().vapid_public_key}


@router.post("/push/subscribe", status_code=204)
def push_subscribe(
    body: schemas.PushSubscriptionIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    prof = db.get(models.Profile, user.id) or models.Profile(user_id=user.id)
    prof.constraints_json = {
        **(prof.constraints_json or {}),
        "push_subscription": body.model_dump(),
    }
    db.add(prof)
    db.commit()
    return None


@router.delete("/push/subscribe", status_code=204)
def push_unsubscribe(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    prof = db.get(models.Profile, user.id)
    if prof and (prof.constraints_json or {}).get("push_subscription"):
        prof.constraints_json = {
            k: v for k, v in prof.constraints_json.items() if k != "push_subscription"
        }
        db.add(prof)
        db.commit()
    return None


# ---------- inputs ----------


@router.post("/activities", status_code=202)
def post_activities(
    body: schemas.ActivitiesIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Upsert normalized activities. `source_ref` (e.g. the HealthKit UUID) dedupes."""
    inserted = updated = 0
    for a in body.activities:
        row = None
        if a.source_ref:
            row = db.scalar(
                select(models.Activity).where(
                    models.Activity.user_id == user.id,
                    models.Activity.source == a.source,
                    models.Activity.source_ref == a.source_ref,
                )
            )
        if row is None:
            row = models.Activity(user_id=user.id, source=a.source, source_ref=a.source_ref)
            db.add(row)
            inserted += 1
        else:
            updated += 1
        row.on_date = a.on
        row.ts = a.ts
        row.type = a.type
        row.duration_min = a.duration_min
        row.intensity = a.intensity.value
    db.commit()
    return {"inserted": inserted, "updated": updated}


@router.get("/activities", response_model=list[schemas.ActivityOut])
def list_activities(
    since: date,
    until: date | None = None,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(models.Activity).where(
        models.Activity.user_id == user.id, models.Activity.on_date >= since
    )
    if until:
        q = q.where(models.Activity.on_date <= until)
    rows = db.scalars(q.order_by(models.Activity.on_date.desc())).all()
    return [
        schemas.ActivityOut(
            id=r.id,
            on=r.on_date,
            type=r.type,
            duration_min=r.duration_min,
            intensity=r.intensity,
            source=r.source,
            source_ref=r.source_ref,
            ts=r.ts,
        )
        for r in rows
    ]


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(
    activity_id: str,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.get(models.Activity, activity_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "activity not found")
    db.delete(row)
    db.commit()
    return None


@router.get("/recovery/{on}", response_model=schemas.RecoveryIn)
def get_recovery(
    on: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.scalar(
        select(models.RecoveryDay).where(
            models.RecoveryDay.user_id == user.id, models.RecoveryDay.on_date == on
        )
    )
    return schemas.RecoveryIn(
        on=on,
        sleep_hours=row.sleep_hours if row else None,
        resting_hr_delta_bpm=row.resting_hr_delta_bpm if row else None,
    )


@router.get("/calendar/{on}", response_model=schemas.CalendarDayIn)
def get_calendar(
    on: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(models.CalEvent)
        .where(models.CalEvent.user_id == user.id, models.CalEvent.on_date == on)
        .order_by(models.CalEvent.start)
    ).all()
    return schemas.CalendarDayIn(
        events=[
            schemas.CalendarEventIn(start=r.start, end=r.end, coarse_type=r.coarse_type)
            for r in rows
        ]
    )


@router.post("/recovery", status_code=202)
def post_recovery(
    body: schemas.RecoveryIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(models.RecoveryDay).where(
            models.RecoveryDay.user_id == user.id, models.RecoveryDay.on_date == body.on
        )
    ) or models.RecoveryDay(user_id=user.id, on_date=body.on)
    row.sleep_hours = body.sleep_hours
    row.resting_hr_delta_bpm = body.resting_hr_delta_bpm
    db.add(row)
    db.commit()
    return {"ok": True}


@router.put("/calendar/{on}", status_code=202)
def put_calendar(
    on: date,
    body: schemas.CalendarDayIn,
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Replace the coarse events for one day. Only start/end/type are stored — never titles."""
    for e in body.events:
        if e.end <= e.start:
            raise HTTPException(422, "event end must be after start")
    db.execute(
        delete(models.CalEvent).where(
            models.CalEvent.user_id == user.id, models.CalEvent.on_date == on
        )
    )
    for e in body.events:
        db.add(
            models.CalEvent(
                user_id=user.id, on_date=on, start=e.start, end=e.end, coarse_type=e.coarse_type
            )
        )
    db.commit()
    return {"events": len(body.events)}


# ---------- outputs ----------


def _brief_out(day: models.Day) -> schemas.BriefOut | None:
    if not day.brief_json:
        return None
    return schemas.BriefOut(
        on=day.on_date,
        lines=day.brief_json["lines"],
        source=day.brief_json["source"],
        status=day.status,
        computed_at=day.computed_at,
    )


def _get_or_compute(db: Session, user: models.User, on: date, recompute: bool) -> models.Day:
    day = db.scalar(
        select(models.Day).where(models.Day.user_id == user.id, models.Day.on_date == on)
    )
    if day is None or recompute or not day.brief_json:
        day = compute_day(db, user, on)
    return day


@router.get("/brief/{on}", response_model=schemas.BriefOut)
def get_brief(
    on: date,
    recompute: bool = Query(default=False),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """The morning brief. Pre-computed by the morning job; computed on demand otherwise."""
    return _brief_out(_get_or_compute(db, user, on, recompute))


@router.post("/brief/{on}/opened", response_model=schemas.BriefOut)
def brief_opened(
    on: date, user: models.User = Depends(current_user), db: Session = Depends(get_db)
):
    """Record that the user opened the brief (PRD leading metric: brief open rate)."""
    day = _get_or_compute(db, user, on, recompute=False)
    if day.status == "planned":
        day.status = "opened"
        db.commit()
    return _brief_out(day)


@router.get("/plan/{on}", response_model=schemas.PlanOut)
def get_plan(
    on: date,
    recompute: bool = Query(default=False),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """The full plan with reason codes and ledger — the answer to "why did you say that?"."""
    day = _get_or_compute(db, user, on, recompute)
    return schemas.PlanOut(on=on, plan=DayPlan.model_validate(day.plan_json), brief=_brief_out(day))
