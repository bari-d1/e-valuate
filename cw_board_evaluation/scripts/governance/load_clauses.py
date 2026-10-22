"""
Load governance clause fixtures (reference/governance/<CODE>.json) into the
database. Idempotent: safe to run repeatedly; clauses are matched on
(code, reference). Sets governance_codes.clauses_loaded.

Usage (from cw_board_evaluation/):
    python scripts/governance/load_clauses.py              # all fixtures
    python scripts/governance/load_clauses.py NCCG_2018    # selected codes

Run scripts/seed_reference_data.py first so the codes are registered.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from app.db.session import SessionLocal
from app.services.governance import fixture_paths, load_clause_fixtures, read_fixture


def main() -> None:
    paths = fixture_paths(sys.argv[1:] or None)
    if not paths:
        sys.exit("No fixtures found.")
    db = SessionLocal()
    try:
        summary = load_clause_fixtures(db, [read_fixture(p) for p in paths])
        db.commit()
    finally:
        db.close()
    for code, counts in summary["codes"].items():
        print(f"{code}: {counts['created']} created, {counts['updated']} updated, {counts['removed']} removed")
    for u in summary["unresolved_citations"]:
        print(f"UNRESOLVED citation: {u['code']} {u['reference']} -> {u['cites']}")


if __name__ == "__main__":
    main()
