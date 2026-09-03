"""Safety rails — hard constraints applied after the rules have run.

These are the numbers the rest of the system may not override. If a rule and a
rail disagree, the rail wins and the plan records which rail fired so every
recommendation stays explainable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.types import DayPlan, FoodFocus, ReasonCode, TrainingRec

# Thresholds. Change them here and nowhere else.
MAX_CONSECUTIVE_HARD_DAYS = 2
MAX_DAYS_WITHOUT_REST = 6
SHORT_SLEEP_HOURS = 6.0
ELEVATED_RESTING_HR_DELTA = 7.0  # bpm above the user's own 7-day baseline
HARD_SESSION_MIN_MINUTES = 30  # a "hard" session shorter than this is treated as moderate
LOAD_HARD_DAY = 60.0  # daily load (duration × intensity weight) that counts as a hard day
MIN_TRAINING_WINDOW_MIN = 30
SHORT_TRAINING_WINDOW_MIN = 50
HEAVY_MEETING_HOURS = 6.0
COMEBACK_GAP_DAYS = 5  # no activity for this many days → gentle first day back

# The training scale, in order. Rails only ever move a value *down* this list.
TRAINING_ORDER = [
    TrainingRec.REST,
    TrainingRec.EASY,
    TrainingRec.SHORT_SESSION,
    TrainingRec.MODERATE,
    TrainingRec.HARD,
]


def cap_training(current: TrainingRec, ceiling: TrainingRec) -> TrainingRec:
    """Return `current` lowered to `ceiling` if it is above it."""
    if TRAINING_ORDER.index(current) > TRAINING_ORDER.index(ceiling):
        return ceiling
    return current


@dataclass
class RailContext:
    consecutive_hard_days: int  # counting back from yesterday
    days_since_rest: int  # days since the last day with no activity
    sleep_hours: float | None
    resting_hr_delta: float | None
    hard_yesterday: bool


def apply_rails(plan: DayPlan, ctx: RailContext) -> DayPlan:
    """Mutates and returns the plan. Every change is recorded in `rails_applied`.

    Idempotent: running it twice records each rail once.
    """
    apply_training_rails(plan, ctx)
    apply_food_rails(plan, ctx)
    return plan


def apply_training_rails(plan: DayPlan, ctx: RailContext) -> DayPlan:
    training = plan.training

    # --- over-training caps ---
    if ctx.consecutive_hard_days >= MAX_CONSECUTIVE_HARD_DAYS:
        capped = cap_training(TrainingRec(training.value), TrainingRec.EASY)
        if capped.value != training.value:
            training.value = capped.value
            training.rails_applied.append(ReasonCode.RAIL_MAX_CONSECUTIVE_HARD)

    if ctx.days_since_rest >= MAX_DAYS_WITHOUT_REST and training.value != TrainingRec.REST.value:
        training.value = TrainingRec.REST.value
        training.rails_applied.append(ReasonCode.RAIL_MIN_REST_PER_WEEK)

    if ctx.sleep_hours is not None and ctx.sleep_hours < SHORT_SLEEP_HOURS:
        capped = cap_training(TrainingRec(training.value), TrainingRec.MODERATE)
        if capped.value != training.value:
            training.value = capped.value
            training.rails_applied.append(ReasonCode.RAIL_NO_HARD_AFTER_SHORT_SLEEP)

    return plan


def apply_food_rails(plan: DayPlan, ctx: RailContext) -> DayPlan:
    training = plan.training
    food = plan.food

    # --- intake floors (qualitative in v1) ---
    # Never suggest eating lighter on the day after a hard session...
    if ctx.hard_yesterday and food.value == FoodFocus.HYDRATE_AND_LIGHTER.value:
        food.value = FoodFocus.FUEL_RECOVERY.value
        food.rails_applied.append(ReasonCode.RAIL_NO_LIGHTER_FOOD_AFTER_HARD)
    # ...nor on a day we are asking the user to train moderately or harder.
    if (
        training.value in (TrainingRec.MODERATE.value, TrainingRec.HARD.value)
        and food.value == FoodFocus.HYDRATE_AND_LIGHTER.value
    ):
        food.value = FoodFocus.STEADY_BALANCED.value
        food.rails_applied.append(ReasonCode.RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY)

    return plan
