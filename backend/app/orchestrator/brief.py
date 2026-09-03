"""Render the 3-line morning brief from a DayPlan.

Two renderers share one output contract:
- `render_template` — deterministic, always available, used when no API key is set and as
  the fallback whenever the LLM output fails validation.
- `render_llm` — Claude turns the plan + reason codes into prose in the user's tone.

Validation is strict: three lines, length-capped, and every integer in the text must be a
number the engine approved. The LLM never gets to introduce a target.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.engine.types import DayPlan, FoodFocus, MovementRec, ReasonCode, TrainingRec
from app.orchestrator.prompts import BRIEF_SYSTEM

log = logging.getLogger(__name__)

MAX_LINE_CHARS = 140


class BriefOutput(BaseModel):
    lines: list[str] = Field(min_length=3, max_length=3)
    source: Literal["llm", "template"] = "template"
    model: str | None = None


# ---------- validation ----------

_INT_RE = re.compile(r"\d+")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def validate_brief(lines: list[str], plan: DayPlan) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    if len(lines) != 3:
        problems.append(f"expected 3 lines, got {len(lines)}")
    allowed = plan.allowed_numbers()
    for i, line in enumerate(lines, 1):
        if not line.strip():
            problems.append(f"line {i} is empty")
        if len(line) > MAX_LINE_CHARS:
            problems.append(f"line {i} is {len(line)} chars (max {MAX_LINE_CHARS})")
        if "\n" in line:
            problems.append(f"line {i} contains a line break")
        # clock times (HH:MM) are allowed only if they are the engine's training window
        for h, m in _TIME_RE.findall(line):
            if int(h) not in allowed or int(m) not in allowed:
                problems.append(f"line {i} contains a time the engine did not approve: {h}:{m}")
        for m in _INT_RE.findall(_TIME_RE.sub("", line)):
            if int(m) not in allowed:
                problems.append(f"line {i} contains a number the engine did not approve: {m}")
    return problems


# ---------- template renderer ----------

_TRAINING_LINE = {
    TrainingRec.REST: "Rest day. No session today",
    TrainingRec.EASY: "Easy day: a gentle walk, jog or mobility session",
    TrainingRec.SHORT_SESSION: "Short session today: {window_minutes} focused minutes is plenty",
    TrainingRec.MODERATE: "A solid, moderate session today",
    TrainingRec.HARD: "Green light for a hard session today",
}
_MOVEMENT_CLAUSE = {
    MovementRec.EASY_WALK: "plus an easy {walk_minutes}-minute walk",
    MovementRec.WALK_BREAKS: "and {walk_breaks} short walk breaks between meetings",
    MovementRec.BASELINE_STEPS: "and your usual {steps} steps",
}
_FOOD_LINE = {
    FoodFocus.FUEL_RECOVERY: "Food: eat to recover. Carbs and protein at every meal, no skipping",
    FoodFocus.PROTEIN_FOCUS: "Food: protein first at each meal, and eat enough to lift well",
    FoodFocus.STEADY_BALANCED: "Food: regular balanced meals. Nothing special needed today",
    FoodFocus.HYDRATE_AND_LIGHTER: (
        "Food: water close by, lighter choices but not less food. Regular meals"
    ),
}
_WHY = {
    ReasonCode.HARD_SESSION_YESTERDAY: "yesterday was a hard session",
    ReasonCode.CONSECUTIVE_HARD_DAYS: "you've stacked hard days",
    ReasonCode.NO_REST_DAY_RECENTLY: "you haven't had a rest day in a week",
    ReasonCode.SHORT_SLEEP: "sleep was short",
    ReasonCode.ELEVATED_RESTING_HR: "your resting heart rate is up",
    ReasonCode.WELL_RESTED: "you're well recovered",
    ReasonCode.BEHIND_WEEKLY_TARGET: "you're behind on this week's sessions",
    ReasonCode.ON_TRACK_WEEKLY_TARGET: "you're on track this week",
    ReasonCode.WEEKLY_TARGET_MET: "this week's sessions are done",
    ReasonCode.NO_TRAINING_WINDOW: "your calendar has no free slot today",
    ReasonCode.TIGHT_TRAINING_WINDOW: "your only free slot is short",
    ReasonCode.TRAINING_WINDOW_FOUND: "there's a good slot in your day",
    ReasonCode.HEAVY_MEETING_DAY: "it's a meeting-heavy day",
    ReasonCode.TRAVEL_DAY: "you're travelling",
    ReasonCode.FUEL_FOR_TRAINING: "today's session needs fuel",
    ReasonCode.REFUEL_AFTER_HARD_SESSION: "yesterday's effort needs refuelling",
    ReasonCode.STRENGTH_DAY_PROTEIN: "it's a strength day",
    ReasonCode.LOW_MOVEMENT_DAY: "it's a low-movement day",
    ReasonCode.DEFAULT_STEADY: "it's an ordinary day",
    ReasonCode.FIRST_DAY_BACK: "it's your first day back",
    ReasonCode.RAIL_MAX_CONSECUTIVE_HARD: "two hard days is the cap",
    ReasonCode.RAIL_MIN_REST_PER_WEEK: "a rest day every week is the rule",
    ReasonCode.RAIL_NO_HARD_AFTER_SHORT_SLEEP: "no hard sessions on short sleep",
    ReasonCode.RAIL_NO_LIGHTER_FOOD_AFTER_HARD: "never lighter food after a hard day",
    ReasonCode.RAIL_NO_LIGHTER_FOOD_ON_TRAINING_DAY: "never lighter food on a training day",
}


def _fmt(template: str, numbers: dict[str, int]) -> str:
    try:
        return template.format(**numbers)
    except KeyError:
        # a number the template expects is missing: strip the clause rather than invent one
        return re.sub(r"\{\w+\}[- ]?\w*", "", template).replace("  ", " ").strip()


def _why_codes(plan: DayPlan) -> list[ReasonCode]:
    """Pick up to two reasons: rails first, then recovery, then calendar, then food."""
    order = [
        *plan.training.rails_applied,
        *plan.food.rails_applied,
        *plan.training.reasons,
        *plan.movement.reasons,
        *plan.food.reasons,
    ]
    skip = {
        ReasonCode.TRAINING_WINDOW_FOUND,
        ReasonCode.ON_TRACK_WEEKLY_TARGET,
        ReasonCode.DEFAULT_STEADY,
    }
    picked: list[ReasonCode] = []
    for code in order:
        if code in picked or code in skip:
            continue
        picked.append(code)
        if len(picked) == 2:
            break
    if not picked:
        picked = [order[0]] if order else [ReasonCode.DEFAULT_STEADY]
    return picked


def render_template(plan: DayPlan) -> BriefOutput:
    training = TrainingRec(plan.training.value)
    line1 = _fmt(_TRAINING_LINE[training], plan.training.numbers)
    movement = MovementRec(plan.movement.value)
    if training in (TrainingRec.REST, TrainingRec.EASY) or movement == MovementRec.WALK_BREAKS:
        line1 += ", " + _fmt(_MOVEMENT_CLAUSE[movement], plan.movement.numbers)
    if plan.training_window and training not in (TrainingRec.REST,):
        w = plan.training_window
        line1 += f". Best slot: {w.start:%H:%M}–{w.end:%H:%M}"
    line1 += "."
    line2 = _FOOD_LINE[FoodFocus(plan.food.value)] + "."
    whys = [_WHY[c] for c in _why_codes(plan)]
    line3 = "Why: " + (whys[0] if len(whys) == 1 else f"{whys[0]}, and {whys[1]}") + "."
    lines = [line1[:MAX_LINE_CHARS], line2[:MAX_LINE_CHARS], line3[:MAX_LINE_CHARS]]
    problems = validate_brief(lines, plan)
    if problems:  # the template is engine-owned, so this is a bug, not user-facing
        raise RuntimeError(f"template brief failed validation: {problems}")
    return BriefOutput(lines=lines, source="template")


# ---------- LLM renderer ----------


class _LLMBrief(BaseModel):
    line_training: str
    line_food: str
    line_why: str


def _plan_payload(plan: DayPlan, tone: str) -> str:
    payload = {
        "date": plan.on.isoformat(),
        "coaching_tone": tone,
        "training": {
            "value": plan.training.value,
            "reasons": [c.value for c in plan.training.reasons],
            "limits_applied": [c.value for c in plan.training.rails_applied],
            "numbers": plan.training.numbers,
            "window": (
                {
                    "start": plan.training_window.start.strftime("%H:%M"),
                    "end": plan.training_window.end.strftime("%H:%M"),
                }
                if plan.training_window
                else None
            ),
        },
        "movement": {
            "value": plan.movement.value,
            "reasons": [c.value for c in plan.movement.reasons],
            "numbers": plan.movement.numbers,
        },
        "food": {
            "value": plan.food.value,
            "reasons": [c.value for c in plan.food.reasons],
            "limits_applied": [c.value for c in plan.food.rails_applied],
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def render_llm(plan: DayPlan, tone: str, model: str) -> BriefOutput | None:
    """Return a validated brief, or None if the model's output was unusable."""
    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": BRIEF_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": _plan_payload(plan, tone)}],
            output_format=_LLMBrief,
        )
    except anthropic.APIError as exc:
        log.warning("brief llm call failed (%s); using template", exc)
        return None
    if response.stop_reason == "refusal" or response.parsed_output is None:
        log.warning("brief llm returned no parsed output (stop_reason=%s)", response.stop_reason)
        return None
    out = response.parsed_output
    lines = [out.line_training.strip(), out.line_food.strip(), out.line_why.strip()]
    problems = validate_brief(lines, plan)
    if problems:
        log.warning("brief llm output rejected: %s", problems)
        return None
    log.info(
        "brief llm ok model=%s in=%s cached=%s out=%s",
        model,
        response.usage.input_tokens,
        getattr(response.usage, "cache_read_input_tokens", None),
        response.usage.output_tokens,
    )
    return BriefOutput(lines=lines, source="llm", model=model)


def render_brief(plan: DayPlan, tone: str = "warm", model: str = "claude-opus-5") -> BriefOutput:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            llm = render_llm(plan, tone, model)
        except ValidationError as exc:  # defensive: the SDK already validates the schema
            log.warning("brief llm schema error: %s", exc)
            llm = None
        if llm is not None:
            return llm
    return render_template(plan)
