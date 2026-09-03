"""Engine v1 rules: training load → training rec; calendar → window + shift; both → food & movement.

Pure functions. No I/O, no randomness, no clock reads — `inputs.on` is "today".
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.engine import rails
from app.engine.types import (
    Activity,
    CalendarEvent,
    DayInputs,
    DayPlan,
    Domain,
    FoodFocus,
    Goal,
    Intensity,
    MovementRec,
    ReasonCode,
    Recommendation,
    TrainingRec,
    TrainingWindow,
)

INTENSITY_WEIGHT = {Intensity.EASY: 1.0, Intensity.MODERATE: 1.5, Intensity.HARD: 2.5}
STRENGTH_TYPES = {"strength", "lifting", "gym"}


# ---------- load & recovery ----------


def daily_load(activities: list[Activity]) -> float:
    return sum(a.duration_min * INTENSITY_WEIGHT[a.intensity] for a in activities)


def is_hard_day(activities: list[Activity]) -> bool:
    if not activities:
        return False
    if any(
        a.intensity == Intensity.HARD and a.duration_min >= rails.HARD_SESSION_MIN_MINUTES
        for a in activities
    ):
        return True
    return daily_load(activities) >= rails.LOAD_HARD_DAY


def _by_day(inputs: DayInputs) -> dict:
    out: dict = {}
    for a in inputs.activities:
        out.setdefault(a.on, []).append(a)
    return out


def consecutive_hard_days(inputs: DayInputs) -> int:
    """Hard days in a row ending yesterday."""
    by_day = _by_day(inputs)
    n = 0
    d = inputs.on - timedelta(days=1)
    while is_hard_day(by_day.get(d, [])):
        n += 1
        d -= timedelta(days=1)
    return n


def days_since_rest(inputs: DayInputs) -> int:
    """Consecutive days ending yesterday that had *any* activity longer than a walk."""
    by_day = _by_day(inputs)
    n = 0
    d = inputs.on - timedelta(days=1)
    while any(a.type != "walk" and a.duration_min >= 15 for a in by_day.get(d, [])):
        n += 1
        d -= timedelta(days=1)
        if n > 14:  # bounded; more history than this changes nothing
            break
    return n


def days_since_any_activity(inputs: DayInputs) -> int | None:
    past = [a.on for a in inputs.activities if a.on < inputs.on]
    if not past:
        return None
    return (inputs.on - max(past)).days


def sessions_this_week(inputs: DayInputs) -> int:
    """Training sessions (not walks) since Monday of the current week, excluding today."""
    monday = inputs.on - timedelta(days=inputs.on.weekday())
    return sum(
        1
        for a in inputs.activities
        if monday <= a.on < inputs.on and a.type != "walk" and a.duration_min >= 15
    )


# ---------- calendar ----------


def _today_window(inputs: DayInputs) -> tuple[datetime, datetime]:
    tz = inputs.calendar[0].start.tzinfo if inputs.calendar else None
    start = datetime.combine(inputs.on, inputs.profile.day_start, tzinfo=tz)
    end = datetime.combine(inputs.on, inputs.profile.day_end, tzinfo=tz)
    return start, end


def free_windows(inputs: DayInputs) -> list[TrainingWindow]:
    day_start, day_end = _today_window(inputs)
    events = sorted(
        (e for e in inputs.calendar if e.end > day_start and e.start < day_end),
        key=lambda e: e.start,
    )
    windows: list[TrainingWindow] = []
    cursor = day_start
    for e in events:
        if e.start > cursor:
            windows.append(TrainingWindow(start=cursor, end=min(e.start, day_end)))
        cursor = max(cursor, e.end)
    if cursor < day_end:
        windows.append(TrainingWindow(start=cursor, end=day_end))
    return windows


def best_training_window(inputs: DayInputs) -> TrainingWindow | None:
    windows = [w for w in free_windows(inputs) if w.minutes >= rails.MIN_TRAINING_WINDOW_MIN]
    if not windows:
        return None
    # Prefer the earliest window that is long enough for a full session; else the longest.
    for w in windows:
        if w.minutes >= rails.SHORT_TRAINING_WINDOW_MIN:
            return w
    return max(windows, key=lambda w: w.minutes)


def meeting_hours(calendar: list[CalendarEvent]) -> float:
    return sum(
        (e.end - e.start).total_seconds() / 3600
        for e in calendar
        if e.coarse_type in ("meeting", "blocked")
    )


def is_travel_day(calendar: list[CalendarEvent]) -> bool:
    return any(e.coarse_type == "travel" for e in calendar)


# ---------- the plan ----------


def plan_day(inputs: DayInputs) -> DayPlan:
    by_day = _by_day(inputs)
    yesterday = inputs.on - timedelta(days=1)
    hard_yesterday = is_hard_day(by_day.get(yesterday, []))
    hard_streak = consecutive_hard_days(inputs)
    rest_gap = days_since_rest(inputs)
    gap_since_any = days_since_any_activity(inputs)
    done_this_week = sessions_this_week(inputs)
    target = inputs.profile.weekly_training_target
    remaining_days = 7 - inputs.on.weekday()  # today included
    sleep = inputs.recovery.sleep_hours
    hr_delta = inputs.recovery.resting_hr_delta_bpm

    # --- training: start from the weekly plan, then let recovery pull it down ---
    training = Recommendation(domain=Domain.TRAINING, value=TrainingRec.MODERATE.value)
    t_reasons: list[ReasonCode] = []
    ceiling = TrainingRec.HARD

    if done_this_week >= target:
        training.value = TrainingRec.EASY.value
        t_reasons.append(ReasonCode.WEEKLY_TARGET_MET)
    elif target - done_this_week >= remaining_days:
        training.value = TrainingRec.MODERATE.value
        t_reasons.append(ReasonCode.BEHIND_WEEKLY_TARGET)
    else:
        training.value = TrainingRec.MODERATE.value
        t_reasons.append(ReasonCode.ON_TRACK_WEEKLY_TARGET)

    if gap_since_any is not None and gap_since_any >= rails.COMEBACK_GAP_DAYS:
        ceiling = rails.cap_training(ceiling, TrainingRec.MODERATE)
        training.value = TrainingRec.EASY.value
        t_reasons.append(ReasonCode.FIRST_DAY_BACK)

    if hard_yesterday:
        ceiling = rails.cap_training(ceiling, TrainingRec.EASY)
        t_reasons.append(ReasonCode.HARD_SESSION_YESTERDAY)
    if hard_streak >= 2:
        t_reasons.append(ReasonCode.CONSECUTIVE_HARD_DAYS)
    if rest_gap >= rails.MAX_DAYS_WITHOUT_REST:
        t_reasons.append(ReasonCode.NO_REST_DAY_RECENTLY)

    if sleep is not None and sleep < rails.SHORT_SLEEP_HOURS:
        ceiling = rails.cap_training(ceiling, TrainingRec.EASY)
        t_reasons.append(ReasonCode.SHORT_SLEEP)
    if hr_delta is not None and hr_delta >= rails.ELEVATED_RESTING_HR_DELTA:
        ceiling = rails.cap_training(ceiling, TrainingRec.EASY)
        t_reasons.append(ReasonCode.ELEVATED_RESTING_HR)
    if (
        not hard_yesterday
        and (sleep is None or sleep >= 7.0)
        and (hr_delta is None or hr_delta < 0)
        and done_this_week < target
        and gap_since_any is not None
        and gap_since_any < rails.COMEBACK_GAP_DAYS
    ):
        t_reasons.append(ReasonCode.WELL_RESTED)
        if inputs.profile.goal == Goal.PERFORM:
            training.value = TrainingRec.HARD.value

    training.value = rails.cap_training(TrainingRec(training.value), ceiling).value

    # --- calendar-aware shift ---
    window = best_training_window(inputs)
    if training.value not in (TrainingRec.REST.value,):
        if window is None:
            if training.value != TrainingRec.EASY.value:
                training.value = TrainingRec.EASY.value
            t_reasons.append(ReasonCode.NO_TRAINING_WINDOW)
        elif window.minutes < rails.SHORT_TRAINING_WINDOW_MIN:
            if training.value in (TrainingRec.MODERATE.value, TrainingRec.HARD.value):
                training.value = TrainingRec.SHORT_SESSION.value
            t_reasons.append(ReasonCode.TIGHT_TRAINING_WINDOW)
        else:
            t_reasons.append(ReasonCode.TRAINING_WINDOW_FOUND)
    if is_travel_day(inputs.calendar):
        t_reasons.append(ReasonCode.TRAVEL_DAY)
        training.value = rails.cap_training(TrainingRec(training.value), TrainingRec.EASY).value
    training.reasons = t_reasons

    # Training rails run *before* food and movement are derived, so they see the final value.
    ctx = rails.RailContext(
        consecutive_hard_days=hard_streak,
        days_since_rest=rest_gap,
        sleep_hours=sleep,
        resting_hr_delta=hr_delta,
        hard_yesterday=hard_yesterday,
    )
    _training_only = DayPlan(
        on=inputs.on,
        training=training,
        food=Recommendation(domain=Domain.FOOD, value=FoodFocus.STEADY_BALANCED.value),
        movement=Recommendation(domain=Domain.MOVEMENT, value=MovementRec.BASELINE_STEPS.value),
    )
    rails.apply_training_rails(_training_only, ctx)
    if window and training.value != TrainingRec.REST.value:
        training.numbers = {"window_minutes": min(window.minutes, 90)}

    # --- movement ---
    mtg_hours = meeting_hours(inputs.calendar)
    movement = Recommendation(domain=Domain.MOVEMENT, value=MovementRec.BASELINE_STEPS.value)
    movement.numbers = {"steps": inputs.profile.baseline_daily_steps}
    if mtg_hours >= rails.HEAVY_MEETING_HOURS:
        movement.value = MovementRec.WALK_BREAKS.value
        movement.reasons.append(ReasonCode.HEAVY_MEETING_DAY)
        movement.numbers["walk_breaks"] = 3
    elif training.value in (TrainingRec.REST.value, TrainingRec.EASY.value):
        movement.value = MovementRec.EASY_WALK.value
        movement.numbers["walk_minutes"] = 20
        if hard_yesterday:
            movement.reasons.append(ReasonCode.HARD_SESSION_YESTERDAY)

    # --- food ---
    food = Recommendation(domain=Domain.FOOD, value=FoodFocus.STEADY_BALANCED.value)
    planned_strength = (
        any(a.type in STRENGTH_TYPES for a in by_day.get(inputs.on, []))
        or inputs.profile.goal == Goal.BUILD
    )
    if hard_yesterday:
        food.value = FoodFocus.FUEL_RECOVERY.value
        food.reasons.append(ReasonCode.REFUEL_AFTER_HARD_SESSION)
    elif training.value in (TrainingRec.HARD.value, TrainingRec.MODERATE.value):
        food.value = (
            FoodFocus.PROTEIN_FOCUS.value if planned_strength else FoodFocus.FUEL_RECOVERY.value
        )
        food.reasons.append(
            ReasonCode.STRENGTH_DAY_PROTEIN if planned_strength else ReasonCode.FUEL_FOR_TRAINING
        )
    elif mtg_hours >= rails.HEAVY_MEETING_HOURS and training.value in (
        TrainingRec.REST.value,
        TrainingRec.EASY.value,
    ):
        food.value = FoodFocus.HYDRATE_AND_LIGHTER.value
        food.reasons.append(ReasonCode.LOW_MOVEMENT_DAY)
    else:
        food.reasons.append(ReasonCode.DEFAULT_STEADY)

    plan = DayPlan(
        on=inputs.on,
        food=food,
        training=training,
        movement=movement,
        training_window=window if training.value != TrainingRec.REST.value else None,
        ledger={
            "yesterday_load": daily_load(by_day.get(yesterday, [])),
            "hard_yesterday": hard_yesterday,
            "consecutive_hard_days": hard_streak,
            "days_since_rest": rest_gap,
            "days_since_any_activity": gap_since_any,
            "sessions_this_week": done_this_week,
            "weekly_target": target,
            "meeting_hours": round(mtg_hours, 1),
            "sleep_hours": sleep,
            "resting_hr_delta_bpm": hr_delta,
        },
    )
    plan = rails.apply_rails(plan, ctx)  # idempotent: re-checks training, applies food rails
    if plan.training.value == TrainingRec.REST.value:
        plan.training_window = None
        plan.training.numbers = {}
    return plan
