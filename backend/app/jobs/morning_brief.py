"""Morning job (M0.5): pre-compute every user's brief so the app opens instantly, then nudge.

Run from cron / a managed scheduler:
    python -m app.jobs.morning_brief            # today
    python -m app.jobs.morning_brief 2026-09-02 # a specific date
    python -m app.jobs.morning_brief --no-push
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import select

from app import models
from app.db import SessionLocal, init_db
from app.jobs.push import send_push
from app.service import compute_day

log = logging.getLogger("corner.morning")


def run(on: date, push: bool = True) -> dict[str, int]:
    init_db()
    stats = {"users": 0, "computed": 0, "pushed": 0, "failed": 0}
    with SessionLocal() as db:
        for user in db.scalars(select(models.User)).all():
            stats["users"] += 1
            try:
                day = compute_day(db, user, on)
                stats["computed"] += 1
            except Exception:  # one user's failure must not stop the batch
                log.exception("brief failed for user %s", user.id)
                db.rollback()
                stats["failed"] += 1
                continue
            prof = db.get(models.Profile, user.id)
            sub = (prof.constraints_json or {}).get("push_subscription") if prof else None
            if (
                push
                and sub
                and day.brief_json
                and send_push(sub, "Your day, in three lines", day.brief_json["lines"][0])
            ):
                stats["pushed"] += 1
    log.info("morning brief %s: %s", on.isoformat(), stats)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", nargs="?", default=date.today().isoformat())
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    run(date.fromisoformat(args.date), push=not args.no_push)


if __name__ == "__main__":
    main()
