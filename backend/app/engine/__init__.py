"""Coaching Engine — deterministic. No LLM code may live in this package.

The engine turns a user's profile, recent activity, and today's calendar into a
DayPlan: one recommendation per domain, each carrying machine-readable reason
codes. Safety rails are applied last and cannot be overridden by any caller.
"""

from app.engine.rules import plan_day
from app.engine.types import (
    Activity,
    CalendarEvent,
    DayInputs,
    DayPlan,
    Domain,
    FoodFocus,
    Intensity,
    MovementRec,
    Profile,
    ReasonCode,
    Recommendation,
    RecoverySignals,
    TrainingRec,
)

__all__ = [
    "plan_day",
    "Activity",
    "CalendarEvent",
    "DayInputs",
    "DayPlan",
    "Domain",
    "FoodFocus",
    "Intensity",
    "MovementRec",
    "Profile",
    "ReasonCode",
    "Recommendation",
    "RecoverySignals",
    "TrainingRec",
]
