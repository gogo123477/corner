from datetime import date, timedelta

TODAY = date(2026, 9, 2)


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_requires_auth(client):
    client.headers.pop("Authorization")
    assert client.get("/v1/profile").status_code == 401
    client.headers["Authorization"] = "Bearer nope"
    assert client.get("/v1/profile").status_code == 401


def test_profile_roundtrip(client):
    r = client.put(
        "/v1/profile",
        json={"goal": "perform", "weekly_training_target": 5, "coaching_tone": "direct"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["goal"] == "perform"
    assert client.get("/v1/profile").json()["weekly_training_target"] == 5


def test_activities_dedupe_by_source_ref(client):
    body = {
        "activities": [
            {
                "on": "2026-09-01",
                "type": "run",
                "duration_min": 60,
                "intensity": "hard",
                "source": "healthkit",
                "source_ref": "hk-1",
            }
        ]
    }
    assert client.post("/v1/activities", json=body).json() == {"inserted": 1, "updated": 0}
    body["activities"][0]["duration_min"] = 65
    assert client.post("/v1/activities", json=body).json() == {"inserted": 0, "updated": 1}


def test_calendar_rejects_inverted_event(client):
    r = client.put(
        "/v1/calendar/2026-09-02",
        json={"events": [{"start": "2026-09-02T10:00:00", "end": "2026-09-02T09:00:00"}]},
    )
    assert r.status_code == 422


def test_brief_end_to_end(client):
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    client.post(
        "/v1/activities",
        json={
            "activities": [
                {"on": yesterday, "type": "run", "duration_min": 60, "intensity": "hard"}
            ]
        },
    )
    client.put(
        "/v1/calendar/2026-09-02",
        json={
            "events": [
                {"start": "2026-09-02T08:00:00", "end": "2026-09-02T12:00:00"},
                {"start": "2026-09-02T13:00:00", "end": "2026-09-02T17:30:00"},
            ]
        },
    )
    client.post("/v1/recovery", json={"on": "2026-09-02", "sleep_hours": 7.5})

    r = client.get("/v1/brief/2026-09-02")
    assert r.status_code == 200, r.text
    brief = r.json()
    assert len(brief["lines"]) == 3
    assert brief["status"] == "planned"
    assert brief["source"] == "template"

    plan = client.get("/v1/plan/2026-09-02").json()["plan"]
    assert plan["training"]["value"] == "easy"
    assert "HARD_SESSION_YESTERDAY" in plan["training"]["reasons"]
    assert plan["movement"]["value"] == "walk_breaks"
    assert plan["food"]["value"] == "fuel_recovery"
    assert plan["ledger"]["meeting_hours"] == 8.5

    opened = client.post("/v1/brief/2026-09-02/opened").json()
    assert opened["status"] == "opened"

    # recompute after new data changes the plan
    client.put("/v1/calendar/2026-09-02", json={"events": []})
    plan2 = client.get("/v1/plan/2026-09-02?recompute=true").json()["plan"]
    assert plan2["movement"]["value"] == "easy_walk"


def test_users_are_isolated(client):
    client.post(
        "/v1/activities",
        json={
            "activities": [
                {"on": "2026-09-01", "type": "run", "duration_min": 60, "intensity": "hard"}
            ]
        },
    )
    client.headers["Authorization"] = "Bearer dev:bob"
    plan = client.get("/v1/plan/2026-09-02").json()["plan"]
    assert plan["ledger"]["hard_yesterday"] is False


def test_morning_job_computes_for_all_users(client):
    from app.jobs.morning_brief import run

    client.get("/v1/profile")  # creates alice
    client.headers["Authorization"] = "Bearer dev:bob"
    client.get("/v1/profile")
    stats = run(TODAY, push=False)
    assert stats["users"] == 2 and stats["computed"] == 2 and stats["failed"] == 0
    assert client.get("/v1/brief/2026-09-02").json()["status"] == "planned"
