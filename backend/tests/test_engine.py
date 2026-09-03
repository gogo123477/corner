from datetime import date, datetime, timedelta

import pytest

from app.engine import (
    Activity,
    CalendarEvent,
    DayInputs,
    FoodFocus,
    Intensity,
    MovementRec,
    Profile,
    ReasonCode,
    TrainingRec,
    plan_day,
)
from app.engine.types import Goal, RecoverySignals

TODAY = date(2026, 9, 2)  # a Wednesday


def act(days_ago: int, minutes: int = 45, intensity=Intensity.MODERATE, type="run"):
    return Activity(
        on=TODAY - timedelta(days=days_ago), type=type, duration_min=minutes, intensity=intensity
    )


def ev(start_h: int, end_h: int, kind="meeting", start_m=0, end_m=0):
    return CalendarEvent(
        start=datetime(2026, 9, 2, start_h, start_m),
        end=datetime(2026, 9, 2, end_h, end_m),
        coarse_type=kind,
    )


def test_quiet_day_on_track_is_moderate_with_window():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(2)], calendar=[ev(9, 12)]))
    assert plan.training.value == TrainingRec.MODERATE.value
    assert ReasonCode.TRAINING_WINDOW_FOUND in plan.training.reasons
    assert plan.training_window is not None
    assert plan.training_window.start.hour == 6  # earliest long-enough gap


def test_hard_yesterday_eases_training_and_refuels():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(1, 60, Intensity.HARD)]))
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.HARD_SESSION_YESTERDAY in plan.training.reasons
    assert plan.food.value == FoodFocus.FUEL_RECOVERY.value
    assert ReasonCode.REFUEL_AFTER_HARD_SESSION in plan.food.reasons
    assert plan.movement.value == MovementRec.EASY_WALK.value


def test_two_hard_days_triggers_rail():
    plan = plan_day(
        DayInputs(
            on=TODAY,
            profile=Profile(goal=Goal.PERFORM, weekly_training_target=6),
            activities=[act(1, 60, Intensity.HARD), act(2, 60, Intensity.HARD)],
        )
    )
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.CONSECUTIVE_HARD_DAYS in plan.training.reasons
    # The rule already eased; the rail should not need to fire, but the plan must be at most EASY.
    assert plan.training.value in (TrainingRec.EASY.value, TrainingRec.REST.value)


def test_six_days_without_rest_forces_rest_day():
    acts = [act(i, 40) for i in range(1, 7)]
    plan = plan_day(DayInputs(on=TODAY, profile=Profile(weekly_training_target=7), activities=acts))
    assert plan.training.value == TrainingRec.REST.value
    assert ReasonCode.RAIL_MIN_REST_PER_WEEK in plan.training.rails_applied
    assert plan.training_window is None


def test_short_sleep_caps_training():
    plan = plan_day(
        DayInputs(on=TODAY, activities=[act(3)], recovery=RecoverySignals(sleep_hours=5.0))
    )
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.SHORT_SLEEP in plan.training.reasons


def test_short_sleep_rail_fires_when_rules_missed_it():
    # Rails must be independent of the rules: feed a plan through apply_rails directly.
    from app.engine.rails import RailContext, apply_rails

    plan = plan_day(DayInputs(on=TODAY, activities=[act(3)]))
    plan.training.value = TrainingRec.HARD.value
    plan = apply_rails(
        plan,
        RailContext(0, 0, sleep_hours=4.5, resting_hr_delta=None, hard_yesterday=False),
    )
    assert plan.training.value == TrainingRec.MODERATE.value
    assert ReasonCode.RAIL_NO_HARD_AFTER_SHORT_SLEEP in plan.training.rails_applied


def test_no_training_window_downgrades_to_easy():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(2)], calendar=[ev(6, 22)]))
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.NO_TRAINING_WINDOW in plan.training.reasons
    assert plan.training_window is None


def test_tight_window_gives_short_session():
    # only a 40-minute gap at 12:00–12:40
    plan = plan_day(
        DayInputs(on=TODAY, activities=[act(2)], calendar=[ev(6, 12), ev(12, 22, start_m=40)])
    )
    assert plan.training.value == TrainingRec.SHORT_SESSION.value
    assert ReasonCode.TIGHT_TRAINING_WINDOW in plan.training.reasons
    assert plan.training_window.minutes == 40


def test_heavy_meeting_day_walk_breaks_and_lighter_food_on_rest():
    acts = [
        act(i, 30) for i in range(1, 7)
    ]  # forces a rest day; 30 min moderate is below the hard-day load
    plan = plan_day(DayInputs(on=TODAY, activities=acts, calendar=[ev(8, 12), ev(13, 17)]))
    assert plan.movement.value == MovementRec.WALK_BREAKS.value
    assert ReasonCode.HEAVY_MEETING_DAY in plan.movement.reasons
    assert plan.food.value == FoodFocus.HYDRATE_AND_LIGHTER.value


def test_never_lighter_food_after_hard_session_even_on_desk_day():
    plan = plan_day(
        DayInputs(
            on=TODAY,
            activities=[act(1, 70, Intensity.HARD)],
            calendar=[ev(8, 12), ev(13, 18)],
        )
    )
    assert plan.food.value == FoodFocus.FUEL_RECOVERY.value


def test_lighter_food_rail_on_training_day():
    from app.engine.rails import RailContext, apply_rails

    plan = plan_day(DayInputs(on=TODAY, activities=[act(3)]))
    plan.training.value = TrainingRec.MODERATE.value
    plan.food.value = FoodFocus.HYDRATE_AND_LIGHTER.value
    plan = apply_rails(plan, RailContext(0, 0, None, None, hard_yesterday=False))
    assert plan.food.value == FoodFocus.STEADY_BALANCED.value
    assert ReasonCode.RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY in plan.food.rails_applied


def test_comeback_after_gap_is_gentle():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(9, 60, Intensity.HARD)]))
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.FIRST_DAY_BACK in plan.training.reasons


def test_weekly_target_met_gives_easy_day():
    plan = plan_day(
        DayInputs(on=TODAY, profile=Profile(weekly_training_target=2), activities=[act(1), act(2)])
    )
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.WEEKLY_TARGET_MET in plan.training.reasons


def test_perform_goal_well_rested_gets_hard_day():
    plan = plan_day(
        DayInputs(
            on=TODAY,
            profile=Profile(goal=Goal.PERFORM, weekly_training_target=5),
            activities=[act(2, 40, Intensity.EASY)],
            recovery=RecoverySignals(sleep_hours=8, resting_hr_delta_bpm=-2),
        )
    )
    assert plan.training.value == TrainingRec.HARD.value
    assert ReasonCode.WELL_RESTED in plan.training.reasons
    assert plan.food.value == FoodFocus.FUEL_RECOVERY.value


def test_strength_day_gets_protein_focus():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(0, 45, type="strength"), act(3)]))
    assert plan.food.value == FoodFocus.PROTEIN_FOCUS.value


def test_travel_day_caps_to_easy():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(3)], calendar=[ev(10, 14, "travel")]))
    assert plan.training.value == TrainingRec.EASY.value
    assert ReasonCode.TRAVEL_DAY in plan.training.reasons


def test_food_never_restricts():
    assert "restrict" not in {f.value for f in FoodFocus}


def test_plan_is_deterministic():
    inputs = DayInputs(
        on=TODAY, activities=[act(1, 60, Intensity.HARD), act(3)], calendar=[ev(9, 11)]
    )
    assert plan_day(inputs).model_dump() == plan_day(inputs).model_dump()


def test_ledger_explains_the_day():
    plan = plan_day(DayInputs(on=TODAY, activities=[act(1, 60, Intensity.HARD)]))
    assert plan.ledger["hard_yesterday"] is True
    assert plan.ledger["yesterday_load"] == 150.0
    assert plan.ledger["days_since_rest"] == 1


@pytest.mark.parametrize("hours", [0.0, 0.5, 3.0])
def test_window_calc_handles_edge_gaps(hours):
    end = datetime(2026, 9, 2, 6, 0) + timedelta(hours=hours)
    cal = [CalendarEvent(start=datetime(2026, 9, 2, 6, 0), end=end)]
    plan = plan_day(DayInputs(on=TODAY, activities=[act(2)], calendar=cal))
    assert plan.training_window is not None
    assert plan.training_window.start == end
