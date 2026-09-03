"""Engine input/output contracts.

Everything here is plain data. The values of the enums are stable strings that
the orchestrator, the API, and the DB all share — treat them as a public contract.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum

from pydantic import BaseModel, Field


class Intensity(StrEnum):
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


class Goal(StrEnum):
    MAINTAIN = "maintain"
    FAT_LOSS = "fat_loss"
    BUILD = "build"
    PERFORM = "perform"


class Domain(StrEnum):
    FOOD = "food"
    TRAINING = "training"
    MOVEMENT = "movement"


class FoodFocus(StrEnum):
    """Qualitative food focus for the day. There is deliberately no 'restrict' value."""

    FUEL_RECOVERY = "fuel_recovery"  # after / around a hard session: carbs + protein, eat enough
    PROTEIN_FOCUS = "protein_focus"  # strength day or build goal
    STEADY_BALANCED = "steady_balanced"  # default: regular meals, nothing special
    HYDRATE_AND_LIGHTER = "hydrate_and_lighter"  # desk-bound day: water, lighter but *not less*


class TrainingRec(StrEnum):
    REST = "rest"
    EASY = "easy"  # recovery-level: easy walk/jog/mobility
    SHORT_SESSION = "short_session"  # 20–30 min because the calendar is tight
    MODERATE = "moderate"
    HARD = "hard"


class MovementRec(StrEnum):
    EASY_WALK = "easy_walk"
    WALK_BREAKS = "walk_breaks"  # meeting-heavy day: several short walks
    BASELINE_STEPS = "baseline_steps"


class ReasonCode(StrEnum):
    """Machine-readable reasons. The LLM turns these into prose; it never invents new ones."""

    # training load / recovery
    HARD_SESSION_YESTERDAY = "HARD_SESSION_YESTERDAY"
    CONSECUTIVE_HARD_DAYS = "CONSECUTIVE_HARD_DAYS"
    NO_REST_DAY_RECENTLY = "NO_REST_DAY_RECENTLY"
    SHORT_SLEEP = "SHORT_SLEEP"
    ELEVATED_RESTING_HR = "ELEVATED_RESTING_HR"
    WELL_RESTED = "WELL_RESTED"
    # weekly plan
    BEHIND_WEEKLY_TARGET = "BEHIND_WEEKLY_TARGET"
    ON_TRACK_WEEKLY_TARGET = "ON_TRACK_WEEKLY_TARGET"
    WEEKLY_TARGET_MET = "WEEKLY_TARGET_MET"
    # calendar
    NO_TRAINING_WINDOW = "NO_TRAINING_WINDOW"
    TIGHT_TRAINING_WINDOW = "TIGHT_TRAINING_WINDOW"
    TRAINING_WINDOW_FOUND = "TRAINING_WINDOW_FOUND"
    HEAVY_MEETING_DAY = "HEAVY_MEETING_DAY"
    TRAVEL_DAY = "TRAVEL_DAY"
    # food
    FUEL_FOR_TRAINING = "FUEL_FOR_TRAINING"
    REFUEL_AFTER_HARD_SESSION = "REFUEL_AFTER_HARD_SESSION"
    STRENGTH_DAY_PROTEIN = "STRENGTH_DAY_PROTEIN"
    LOW_MOVEMENT_DAY = "LOW_MOVEMENT_DAY"
    DEFAULT_STEADY = "DEFAULT_STEADY"
    # comeback
    FIRST_DAY_BACK = "FIRST_DAY_BACK"
    # rails (always prefixed RAIL_ so they are auditable)
    RAIL_MAX_CONSECUTIVE_HARD = "RAIL_MAX_CONSECUTIVE_HARD"
    RAIL_MIN_REST_PER_WEEK = "RAIL_MIN_REST_PER_WEEK"
    RAIL_NO_HARD_AFTER_SHORT_SLEEP = "RAIL_NO_HARD_AFTER_SHORT_SLEEP"
    RAIL_NO_LIGHTER_FOOD_AFTER_HARD = "RAIL_NO_LIGHTER_FOOD_AFTER_HARD"
    RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY = "RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY"


# ---------- inputs ----------


class Profile(BaseModel):
    goal: Goal = Goal.MAINTAIN
    weekly_training_target: int = Field(default=3, ge=0, le=7)
    baseline_daily_steps: int = Field(default=7000, ge=0)
    day_start: time = time(6, 0)
    day_end: time = time(22, 0)
    coaching_tone: str = "warm"  # free text for the orchestrator; the engine ignores it


class Activity(BaseModel):
    """A normalized movement event (from HealthKit, Health Connect, or manual entry)."""

    on: date
    type: str = "other"  # run | strength | cycle | swim | walk | other
    duration_min: int = Field(ge=0)
    intensity: Intensity = Intensity.MODERATE


class CalendarEvent(BaseModel):
    start: datetime
    end: datetime
    coarse_type: str = "meeting"  # meeting | travel | personal | blocked


class RecoverySignals(BaseModel):
    sleep_hours: float | None = None
    resting_hr_delta_bpm: float | None = None  # today's resting HR minus 7-day baseline


class DayInputs(BaseModel):
    on: date
    profile: Profile = Profile()
    activities: list[Activity] = []  # any window; the engine looks back 7 days
    calendar: list[CalendarEvent] = []  # today's events
    recovery: RecoverySignals = RecoverySignals()


# ---------- outputs ----------


class TrainingWindow(BaseModel):
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


class Recommendation(BaseModel):
    domain: Domain
    value: str  # FoodFocus | TrainingRec | MovementRec value
    reasons: list[ReasonCode] = []
    rails_applied: list[ReasonCode] = []
    # small, engine-owned numbers the brief may quote (the LLM may not invent others)
    numbers: dict[str, int] = {}


class DayPlan(BaseModel):
    on: date
    food: Recommendation
    training: Recommendation
    movement: Recommendation
    training_window: TrainingWindow | None = None
    # the engine's own account of the day; useful for "why did you say that?"
    ledger: dict[str, float | int | str | bool | None] = {}

    def all_reasons(self) -> list[ReasonCode]:
        seen: list[ReasonCode] = []
        for rec in (self.training, self.food, self.movement):
            for code in rec.reasons + rec.rails_applied:
                if code not in seen:
                    seen.append(code)
        return seen

    def allowed_numbers(self) -> set[int]:
        out: set[int] = set()
        for rec in (self.training, self.food, self.movement):
            out.update(rec.numbers.values())
        if self.training_window:
            w = self.training_window
            out.update({w.start.hour, w.end.hour, w.start.minute, w.end.minute})
            out.add(self.training_window.minutes)
        return out
