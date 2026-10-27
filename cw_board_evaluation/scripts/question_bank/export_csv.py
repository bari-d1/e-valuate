"""
Write a question bank fixture (JSON) out as a flat CSV for review in a spreadsheet.

The JSON is the source of truth; regenerate the CSV after editing it:

    python scripts/question_bank/export_csv.py                      # draft_bank.json -> draft_bank.csv
    python scripts/question_bank/export_csv.py path/to/bank.json    # -> path/to/bank.csv
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.domain.question_rules import describe_rule  # noqa: E402

DEFAULT_FIXTURE = ROOT / "reference" / "question_bank" / "draft_bank.json"

COLUMNS = [
    "code", "version", "status", "priority", "section", "text", "answer_type", "options", "scale",
    "subject_types", "subject_binding", "respondent_rule_plain", "activation_rule_plain",
    "theme_code", "evidence_source_code", "known_from", "known_from_behaviour", "placeholders",
    "governance_refs", "guidance", "review_notes", "source_refs",
    "why_subject_types", "why_subject_binding", "why_respondent_rule", "why_activation_rule",
    "why_theme", "why_evidence_source", "why_governance_refs", "why_priority",
    "respondent_rule", "activation_rule", "weight", "sort_order",
]


def _scale(scale: Any) -> str:
    if not scale:
        return ""
    labels = scale.get("labels") or {}
    text = " | ".join(f"{k} {labels[k]}" for k in sorted(labels, key=int))
    return text + (" | Don't know" if scale.get("dont_know") else "")


def _source(ref: Dict[str, Any]) -> str:
    if ref.get("derived_from"):
        return f"from bank item {ref['derived_from']}"
    return f"{ref.get('form')} {ref.get('item')}".strip()


def item_row(item: Dict[str, Any]) -> Dict[str, Any]:
    notes = item.get("tag_notes") or {}
    refs = item.get("source_refs") or []
    return {
        "code": item["code"],
        "version": item.get("version", 1),
        "status": item.get("status", "draft"),
        "priority": item.get("priority", "standard"),
        "section": (refs[0].get("section") or refs[0].get("derived_section", "")) if refs else "",
        "text": item["text"],
        "answer_type": item["answer_type"],
        "options": " | ".join(item.get("options") or []),
        "scale": _scale(item.get("scale")),
        "subject_types": "; ".join(item.get("subject_types") or []),
        "subject_binding": item.get("subject_binding", ""),
        "respondent_rule_plain": describe_rule(item.get("respondent_rule")),
        "activation_rule_plain": describe_rule(item.get("activation_rule")),
        "theme_code": item.get("theme_code") or "",
        "evidence_source_code": item.get("evidence_source_code") or "",
        "known_from": item.get("known_from") or "",
        "known_from_behaviour": item.get("known_from_behaviour") if item.get("known_from") else "",
        "placeholders": "; ".join(item.get("placeholders") or []),
        "governance_refs": "; ".join(f"{r['code']} {r['reference']}" for r in item.get("governance_refs") or []),
        "guidance": item.get("guidance") or "",
        "review_notes": item.get("review_notes") or "",
        "source_refs": "; ".join(_source(r) for r in refs),
        **{f"why_{k}": (notes.get(k) or {}).get("reason", "") for k in (
            "subject_types", "subject_binding", "respondent_rule", "activation_rule", "theme",
            "evidence_source", "governance_refs", "priority")},
        "respondent_rule": json.dumps(item.get("respondent_rule")) if item.get("respondent_rule") else "",
        "activation_rule": json.dumps(item.get("activation_rule")) if item.get("activation_rule") else "",
        "weight": item.get("weight", 1),
        "sort_order": item.get("sort_order", 0),
    }


def rows(fixture: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [item_row(i) for i in fixture["items"]]


def write_csv(fixture: Dict[str, Any], path: Path) -> int:
    data = rows(fixture)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(data)
    return len(data)


def main(argv: List[str]) -> int:
    src = Path(argv[0]) if argv else DEFAULT_FIXTURE
    fixture = json.loads(src.read_text(encoding="utf-8"))
    out = src.with_suffix(".csv")
    n = write_csv(fixture, out)
    print(f"Wrote {n} items to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
