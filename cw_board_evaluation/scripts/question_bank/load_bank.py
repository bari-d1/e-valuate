"""
Load a question bank fixture (reference/question_bank/draft_bank.json by
default) into the database. Idempotent: items are matched on (code, version)
and an item already loaded is left alone, so consultants' edits are never
overwritten. Every item is validated (content, rules, tag codes) and its
governance clause references resolved; anything that doesn't load is listed.

Usage (from cw_board_evaluation/):
    python scripts/question_bank/load_bank.py                         # the draft bank
    python scripts/question_bank/load_bank.py path/to/bank.json       # another fixture
    python scripts/question_bank/load_bank.py --update-drafts         # also refresh items still in draft
    python scripts/question_bank/load_bank.py --check                 # validate only, roll back

Run scripts/seed_reference_data.py and scripts/governance/load_clauses.py
first so tag codes and clauses exist. Exits 1 if any item failed to load.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, str(ROOT))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from app.db.session import SessionLocal
from app.services.question_bank import load_fixture

DEFAULT_FIXTURE = ROOT / "reference" / "question_bank" / "draft_bank.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fixture", nargs="?", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--update-drafts", action="store_true", help="refresh items that are still drafts")
    parser.add_argument("--check", action="store_true", help="validate and report, but don't save")
    args = parser.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    db = SessionLocal()
    try:
        summary = load_fixture(db, fixture, update_drafts=args.update_drafts)
        if args.check:
            db.rollback()
        else:
            db.commit()
    finally:
        db.close()

    verb = "would be" if args.check else "were"
    print(f"{len(summary['created'])} items {verb} created, {len(summary['updated'])} updated, "
          f"{len(summary['unchanged'])} already loaded (left alone).")
    for e in summary["errors"]:
        print(f"NOT LOADED {e['item']}:")
        for msg in e["errors"]:
            print(f"    - {msg}")
    for u in summary["unresolved_clauses"]:
        print(f"UNRESOLVED clause on {u['item']}: {u['code']} {u['reference']} (item loaded without it)")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
