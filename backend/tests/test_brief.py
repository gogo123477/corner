from datetime import date, datetime, timedelta

from app.engine import Activity, CalendarEvent, DayInputs, Intensity, plan_day
from app.orchestrator.brief import render_brief, render_template, validate_brief

TODAY = date(2026, 9, 2)


def _plan(**kw):
    return plan_day(DayInputs(on=TODAY, **kw))


def test_template_brief_has_three_short_lines():
    plan = _plan(
        activities=[
            Activity(on=TODAY - timedelta(days=1), duration_min=60, intensity=Intensity.HARD)
        ],
        calendar=[CalendarEvent(start=datetime(2026, 9, 2, 9), end=datetime(2026, 9, 2, 12))],
    )
    brief = render_template(plan)
    assert len(brief.lines) == 3
    assert all(len(line) <= 140 for line in brief.lines)
    assert brief.lines[0].startswith("Easy day")
    assert brief.lines[1].startswith("Food: eat to recover")
    assert "hard session" in brief.lines[2]
    assert brief.source == "template"


def test_template_mentions_window_when_present():
    plan = _plan(
        activities=[Activity(on=TODAY - timedelta(days=2), duration_min=45)],
        calendar=[CalendarEvent(start=datetime(2026, 9, 2, 6), end=datetime(2026, 9, 2, 9))],
    )
    brief = render_template(plan)
    assert "09:00" in brief.lines[0]


def test_template_rest_day_has_no_window_and_rail_reason():
    acts = [Activity(on=TODAY - timedelta(days=i), duration_min=30) for i in range(1, 7)]
    brief = render_template(_plan(activities=acts))
    assert brief.lines[0].startswith("Rest day")
    assert "slot" not in brief.lines[0]
    assert "rest day every week" in brief.lines[2]


def test_template_is_the_default_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    plan = _plan(activities=[Activity(on=TODAY - timedelta(days=2), duration_min=45)])
    assert render_brief(plan).source == "template"


def test_validation_rejects_invented_numbers():
    plan = _plan(activities=[Activity(on=TODAY - timedelta(days=2), duration_min=45)])
    ok = ["A solid session today.", "Food: regular meals.", "Why: on track."]
    assert validate_brief(ok, plan) == []
    bad = ["Run 10 km today.", "Eat 1800 calories.", "Why: on track."]
    problems = validate_brief(bad, plan)
    assert any("10" in p for p in problems) and any("1800" in p for p in problems)


def test_validation_allows_engine_numbers():
    plan = _plan(activities=[Activity(on=TODAY - timedelta(days=2), duration_min=45)])
    steps = plan.movement.numbers["steps"]
    assert validate_brief([f"Aim for {steps} steps.", "Food: steady.", "Why: fine."], plan) == []


def test_validation_rejects_wrong_shape():
    plan = _plan()
    assert validate_brief(["only one"], plan)
    assert validate_brief(["a" * 141, "b", "c"], plan)
    assert validate_brief(["a\nb", "b", "c"], plan)


def test_llm_output_falls_back_to_template_when_invalid(monkeypatch):
    from app.orchestrator import brief as brief_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(brief_mod, "render_llm", lambda plan, tone, model: None)
    plan = _plan(activities=[Activity(on=TODAY - timedelta(days=2), duration_min=45)])
    assert render_brief(plan).source == "template"


def test_every_plan_shape_renders(monkeypatch):
    """Sweep a grid of situations; the template must never raise."""
    from itertools import product

    for hard_y, sleep, mtg, gap in product([False, True], [None, 5.0, 8.0], [0, 8], [1, 7]):
        acts = [
            Activity(
                on=TODAY - timedelta(days=gap),
                duration_min=60,
                intensity=Intensity.HARD if hard_y else Intensity.MODERATE,
            )
        ]
        cal = (
            [CalendarEvent(start=datetime(2026, 9, 2, 8), end=datetime(2026, 9, 2, 8 + mtg))]
            if mtg
            else []
        )
        from app.engine.types import RecoverySignals

        plan = plan_day(
            DayInputs(
                on=TODAY, activities=acts, calendar=cal, recovery=RecoverySignals(sleep_hours=sleep)
            )
        )
        assert len(render_template(plan).lines) == 3
