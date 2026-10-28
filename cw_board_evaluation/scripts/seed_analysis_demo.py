"""
Seed a VAL-001-style evaluation with submitted answers that contain the planted
analysis patterns (tests/analysis_seed.py), for trying the Findings page.
Placeholder names and emails only.

Usage (from cw_board_evaluation/, after seed_reference_data.py, governance/load_clauses.py
and question_bank/load_bank.py):
    python scripts/seed_analysis_demo.py                 # evaluation VAL-ANALYSIS
    python scripts/seed_analysis_demo.py --eid VAL-002   # another id

Approves every draft question bank item (so assembly can use them), builds the
company, board, committees and evaluation, assembles and approves every set, then
answers and submits every form. Refuses to touch an evaluation id that already exists.
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from sqlalchemy import update

from app.db.models import Evaluation, QuestionBankItem
from app.db.session import SessionLocal
from app.services import question_assembly as qa
from app.services import question_sets as qs
from tests.analysis_seed import seed_planted
from tests.val001 import build_val001


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--eid", default="VAL-ANALYSIS")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if db.get(Evaluation, args.eid):
            print(f"Evaluation {args.eid} already exists; choose another --eid.")
            return 1
        db.execute(update(QuestionBankItem).where(QuestionBankItem.status == "draft").values(status="approved"))
        ev, parts, _ = build_val001(db, eid=args.eid)
        ev.name, ev.status = "2025 Board Evaluation", "live"
        qa.run_assembly(db, qa.create_run(db, ev))
        for p in parts.values():
            qs.approve_set(db, qs.question_set(db, p.id), "Seed script", override_reason="Demo data")
        seed_planted(db, ev, parts)
        db.commit()
        print(f"Seeded {args.eid}: 7 participants, all submitted. Open it and go to Findings.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
