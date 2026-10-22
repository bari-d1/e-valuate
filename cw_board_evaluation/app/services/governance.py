"""
app.services.governance
-----------------------
Database helpers for the governance code library.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GovernanceClause, GovernanceClauseSubjectType, GovernanceCode, SubjectType, Theme
from app.domain.governance import GOVERNANCE_CODES

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "reference" / "governance"
TAG_RULES_PATH = FIXTURE_DIR / "tag_rules.csv"


def seed_governance_codes(db: Session) -> Dict[str, int]:
    """
    Register any missing governance codes (metadata only). Existing rows are
    left untouched: a new edition is a new code, never an overwrite.
    Flushes but does not commit.
    """
    existing = set(db.execute(select(GovernanceCode.code)).scalars().all())
    created = 0
    for spec in GOVERNANCE_CODES:  # base code first (supplements_code FK)
        if spec["code"] in existing:
            continue
        db.add(GovernanceCode(jurisdiction="NG", clauses_loaded=False, **spec))
        db.flush()
        created += 1
    return {"governance_codes": created}


def read_fixture(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_clause_fixtures(db: Session, fixtures: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Load clause fixtures idempotently, keyed by (code, reference):
    existing clauses are updated in place (ids stay stable), new ones created,
    and clauses no longer in a fixture removed. Parents and cross-code
    citations are resolved after all fixtures are in, so order doesn't matter.
    Sets governance_codes.clauses_loaded. Flushes but does not commit.
    """
    fixtures = list(fixtures)
    summary: Dict[str, Any] = {"codes": {}, "unresolved_citations": []}

    by_code: Dict[str, Dict[str, GovernanceClause]] = {}
    for fx in fixtures:
        code = fx["code"]
        gc = db.get(GovernanceCode, code)
        if gc is None:
            raise ValueError(f"Governance code {code} is not registered; run scripts/seed_reference_data.py first.")

        existing = {
            c.reference: c
            for c in db.execute(select(GovernanceClause).where(GovernanceClause.code == code)).scalars().all()
        }
        wanted = {row["reference"] for row in fx["clauses"]}
        created = updated = 0
        for row in fx["clauses"]:
            c = existing.get(row["reference"])
            if c is None:
                c = GovernanceClause(code=code, reference=row["reference"])
                db.add(c)
                existing[row["reference"]] = c
                created += 1
            else:
                updated += 1
            c.level = row["level"]
            c.heading = row.get("heading")
            c.text = row.get("text") or ""
            c.sort_order = int(row["sort_order"])
        removed = 0
        for ref, c in list(existing.items()):
            if ref not in wanted:
                db.delete(c)
                del existing[ref]
                removed += 1
        db.flush()
        by_code[code] = existing
        summary["codes"][code] = {"created": created, "updated": updated, "removed": removed}

    def lookup(code: str, ref: str) -> Optional[GovernanceClause]:
        if code not in by_code:
            clauses = db.execute(select(GovernanceClause).where(GovernanceClause.code == code)).scalars().all()
            by_code[code] = {c.reference: c for c in clauses}
        return by_code[code].get(ref)

    for fx in fixtures:
        code = fx["code"]
        for row in fx["clauses"]:
            c = by_code[code][row["reference"]]
            parent_ref = row.get("parent_reference")
            c.parent_id = by_code[code][parent_ref].id if parent_ref else None
            target_id = None
            if row.get("cites"):
                target_code, target_ref = row["cites"].split(":", 1)
                target = lookup(target_code, target_ref)
                if target is None:
                    summary["unresolved_citations"].append({"code": code, "reference": row["reference"], "cites": row["cites"]})
                else:
                    target_id = target.id
            c.cites_clause_id = target_id
        db.get(GovernanceCode, code).clauses_loaded = True
    db.flush()
    return summary


def _norm_heading(s: Optional[str]) -> str:
    s = (s or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def read_tag_rules(path: Path = TAG_RULES_PATH) -> List[Dict[str, Any]]:
    """Heading -> tags rules from the reviewable CSV (code, heading, subject_types, theme, note)."""
    rules = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rules.append({
                "code": row["code"].strip(),
                "heading": row["heading"].strip(),
                "subject_types": [x.strip() for x in (row.get("subject_types") or "").split(";") if x.strip()],
                "theme": (row.get("theme") or "").strip() or None,
            })
    return rules


def apply_tag_rules(db: Session, codes: Iterable[str], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tag clauses deterministically from their headings (no LLM):
    a clause whose heading matches a rule gets exactly that rule's subject
    types and theme; other clauses inherit their parent's tags. Parts are
    never tagged (Part headings repeat principle headings, e.g. Part D).
    Replaces existing tags, so it is idempotent. Flushes but does not commit.
    """
    known_subjects = set(db.execute(select(SubjectType.code)).scalars().all())
    known_themes = set(db.execute(select(Theme.code)).scalars().all())
    bad = []
    for r in rules:
        bad += [f"{r['code']} '{r['heading']}': unknown subject type {s}" for s in r["subject_types"] if s not in known_subjects]
        if r["theme"] and r["theme"] not in known_themes:
            bad.append(f"{r['code']} '{r['heading']}': unknown theme {r['theme']}")
    if bad:
        raise ValueError("Invalid tag rules: " + "; ".join(bad))

    result: Dict[str, Any] = {"codes": {}, "unmatched_rules": [], "untagged": []}
    matched = set()
    for code in codes:
        by_heading = {(r["code"], _norm_heading(r["heading"])): r for r in rules}
        clauses = db.execute(
            select(GovernanceClause).where(GovernanceClause.code == code).order_by(GovernanceClause.sort_order)
        ).scalars().all()
        tags: Dict[Any, Any] = {}  # clause id -> (subjects, theme); parents come before children
        counts = {"rule": 0, "inherited": 0, "untagged": 0}
        for c in clauses:
            rule = by_heading.get((code, _norm_heading(c.heading))) if c.level != "part" and c.heading else None
            if rule:
                subjects, theme = list(rule["subject_types"]), rule["theme"]
                matched.add((code, _norm_heading(rule["heading"])))
                counts["rule"] += 1
            elif c.parent_id in tags:
                subjects, theme = tags[c.parent_id]
                counts["inherited"] += 1 if (subjects or theme) else 0
            else:
                subjects, theme = [], None
            tags[c.id] = (subjects, theme)
            c.theme_code = theme
            c.subject_type_links = [GovernanceClauseSubjectType(subject_type_code=s) for s in subjects]
            if not subjects and not theme and c.level != "part":
                counts["untagged"] += 1
                result["untagged"].append({"code": code, "reference": c.reference, "heading": c.heading})
        result["codes"][code] = counts
    codes = set(codes)
    result["unmatched_rules"] = [
        {"code": r["code"], "heading": r["heading"]}
        for r in rules
        if r["code"] in codes and (r["code"], _norm_heading(r["heading"])) not in matched
    ]
    db.flush()
    return result


def fixture_paths(codes: Optional[List[str]] = None) -> List[Path]:
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    if codes:
        paths = [p for p in paths if p.stem in set(codes)]
    return paths
