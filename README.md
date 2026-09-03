# Corner — cross-domain personal coach

Phase 0 ("Morning Brief that reads your week") of the plan in
[`docs/technical-design.md`](docs/technical-design.md).

```
backend/   FastAPI · deterministic coaching engine · LLM orchestrator · morning job
mobile/    Expo (iOS first) · Morning Brief screen · HealthKit + calendar sync
```

## What works today

| Milestone | Status |
|---|---|
| M0.1 Skeleton: API, Postgres/SQLite, bearer auth (dev + HS256 JWT) | done |
| M0.2 HealthKit + calendar read | client code written, needs a device build to verify |
| M0.3 Deterministic engine v1 with reason codes and safety rails | done, 22 unit tests |
| M0.4 Orchestrator: 3-line brief (Claude, strict validation, template fallback) | done |
| M0.5 Morning job pre-computes briefs + Expo push nudge | done |

## Backend

```bash
cd backend
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
cp .env.example .env          # defaults: SQLite, dev auth, no LLM key → template briefs
.venv/bin/pytest              # 39 tests
.venv/bin/uvicorn app.main:app --reload   # http://localhost:8000/docs
```

Try it with the dev token:

```bash
H='Authorization: Bearer dev:me'; C='Content-Type: application/json'
curl -X POST localhost:8000/v1/activities -H "$H" -H "$C" \
  -d '{"activities":[{"on":"2026-09-01","type":"run","duration_min":70,"intensity":"hard"}]}'
curl -X PUT localhost:8000/v1/calendar/2026-09-02 -H "$H" -H "$C" \
  -d '{"events":[{"start":"2026-09-02T09:00:00","end":"2026-09-02T17:00:00"}]}'
curl localhost:8000/v1/brief/2026-09-02 -H "$H"
curl localhost:8000/v1/plan/2026-09-02 -H "$H"     # reason codes + ledger ("why did you say that?")
```

Morning job (cron / managed scheduler):

```bash
.venv/bin/python -m app.jobs.morning_brief            # today, all users, push if token set
.venv/bin/python -m app.jobs.morning_brief --no-push
```

### How it is wired

- `app/engine/` — **no LLM code allowed here.** `rules.py` turns profile + 14 days of
  activities + today's calendar + recovery signals into a `DayPlan`: one recommendation
  per domain (training, food, movement) with `ReasonCode`s. `rails.py` holds the hard
  limits (max 2 consecutive hard days, rest day every 6, no hard session on short sleep,
  never "lighter" food after a hard day or on a training day). Rails run after rules and
  record what they changed. There is no "restrict" food value by design.
- `app/orchestrator/` — turns the plan into three lines. With `ANTHROPIC_API_KEY` set,
  Claude writes them (`client.messages.parse` with a strict schema; the system prompt is
  cached). Every output is validated: exactly 3 lines, ≤140 chars, and **every number
  must be one the engine approved**. Anything else falls back to the deterministic
  template renderer, which is also what runs with no key.
- `app/service.py` — `compute_day()` is the one operation both the API and the morning
  job call: load inputs → engine → brief → persist `days` + `recommendations`.
- `app/auth.py` — `CORNER_AUTH_MODE=dev` accepts `Bearer dev:<name>`; `jwt` verifies an
  HS256 token (Supabase Auth's default) and uses `sub` as the account reference.

Privacy defaults (design §6): calendar rows store only start/end/coarse type; activities
are normalized (no raw samples); health-derived columns carry `info={"sensitive": True}`
so an export path can exclude them. Column-level encryption is a Phase 1 item.

### Environment

| Variable | Default | Notes |
|---|---|---|
| `CORNER_DATABASE_URL` | `sqlite:///./corner.db` | prod: `postgresql+psycopg://…` |
| `CORNER_AUTH_MODE` | `dev` | `jwt` for production |
| `CORNER_JWT_SECRET` | — | required in `jwt` mode |
| `CORNER_BRIEF_MODEL` | `claude-opus-5` | any current Claude model id |
| `ANTHROPIC_API_KEY` | unset | unset = template briefs, no LLM calls |

## Mobile

Expo + TypeScript, iOS first. `npm install && npx expo run:ios` (HealthKit needs a dev
build, not Expo Go). Set `EXPO_PUBLIC_API_BASE` to the backend URL.

- `src/screens/MorningBriefScreen.tsx` — the three lines, "Why did you say that?" with
  reason codes in plain words, pull-to-refresh re-syncs and recomputes.
- `src/sync/health.ts` — HealthKit workouts → normalized activities (type, minutes, coarse
  intensity). Raw samples stay on the phone.
- `src/sync/calendar.ts` — today's events → start/end/coarse type only.

The mobile code has **not** been built or run in this environment (no iOS toolchain);
treat it as a reviewed scaffold until the first device build.

## Next

1. Run the backend against Neon/Supabase Postgres and switch auth to `jwt`.
2. First device build; verify HealthKit + calendar permissions and the brief open flow.
3. Spike 0 (food estimation) before any Phase 1 work — see the design doc §8.
