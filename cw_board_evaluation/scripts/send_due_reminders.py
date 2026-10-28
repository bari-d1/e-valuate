"""
Send the automatic reminders that are due now, across every open evaluation
with reminders switched on. Safe to run as often as you like, and from more
than one machine at once: a reminder slot is only ever sent once.

Usage (from cw_board_evaluation/):
    python scripts/send_due_reminders.py              # send what's due
    python scripts/send_due_reminders.py --dry-run    # list who would be reminded and why; send nothing
    python scripts/send_due_reminders.py --now 2026-11-03T09:00:00+00:00 --dry-run   # as if at another time

Example cron line (weekdays at 09:00 server time; reminders skip weekends anyway):
    # 0 9 * * 1-5  cd /srv/e-valuate/cw_board_evaluation && .venv/bin/python scripts/send_due_reminders.py >> /var/log/e-valuate-reminders.log 2>&1

Exits 1 if any reminder failed to send.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from app.db.session import SessionLocal
from app.services.tracking import send_due_reminders


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list who would be reminded; send nothing")
    parser.add_argument("--now", help="ISO date-time to run as (for testing a schedule)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    db = SessionLocal()
    try:
        out = send_due_reminders(db, now, dry_run=args.dry_run)
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{now:%Y-%m-%d %H:%M} UTC: {out['evaluations']} evaluation(s) with reminders on.")
        if args.dry_run:
            for x in out["would_remind"]:
                print(f"  would remind {x['name']} ({x['evaluation_id']}): {x['reason']}")
        for x in out["sent"]:
            print(f"  reminded {x['name']} ({x['evaluation_id']}){' (final)' if x['final'] else ''}")
        for x in out["failed"]:
            print(f"  FAILED {x['name']} ({x['evaluation_id']}): {x.get('reason')}")
        print(f"{len(out['sent'])} sent, {len(out['failed'])} failed, "
              f"{len(out['would_remind'])} would be sent, {len(out['skipped'])} not due.")
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
