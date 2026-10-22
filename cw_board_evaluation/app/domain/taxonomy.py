"""
app.domain.taxonomy
-------------------
Tagging vocabulary for questions, and the single source of truth for mapping
legacy assignment types and participant roles to subject types.

Three tag types:
- Subject type: WHO or WHAT is evaluated (fixed list confirmed by the client).
- Theme: WHICH ASPECT is evaluated (provisional; names may change, so they live
  in the `themes` table, not in code paths).
- Evidence source: WHAT KIND of evidence a question gathers.

The lists below are the reference data. They are seeded into the lookup tables
by the Alembic migration (which keeps its own frozen copy) and by
scripts/seed_reference_data.py. Application code should read names from the
database; only the codes are relied on here.
"""

from __future__ import annotations

from typing import Dict, List

# ----------------------------
# Subject types
# ----------------------------

CARDINALITY_SINGLE = "single"
CARDINALITY_PER_PERSON = "per_person"
CARDINALITY_PER_COMMITTEE = "per_committee"
CARDINALITIES = (CARDINALITY_SINGLE, CARDINALITY_PER_PERSON, CARDINALITY_PER_COMMITTEE)

SUBJECT_TYPES: List[Dict[str, object]] = [
    {"code": "BOARD", "name": "Board as a whole", "description": "The board as a collective body.", "cardinality": CARDINALITY_SINGLE},
    {"code": "CHAIR", "name": "Board chairman", "description": "The chair of the board.", "cardinality": CARDINALITY_SINGLE},
    {"code": "MD_CEO", "name": "Managing Director / CEO", "description": "The managing director or chief executive.", "cardinality": CARDINALITY_SINGLE},
    {"code": "ED", "name": "Executive director", "description": "An executive director.", "cardinality": CARDINALITY_PER_PERSON},
    {"code": "NED", "name": "Non-executive director", "description": "A non-executive director.", "cardinality": CARDINALITY_PER_PERSON},
    {"code": "INED", "name": "Independent NED", "description": "An independent non-executive director.", "cardinality": CARDINALITY_PER_PERSON},
    {"code": "COMMITTEE", "name": "Board committee", "description": "A committee of the board.", "cardinality": CARDINALITY_PER_COMMITTEE},
    {"code": "COMPANY_SECRETARY", "name": "Company secretary / secretariat", "description": "The company secretary or board secretariat.", "cardinality": CARDINALITY_SINGLE},
]

# ----------------------------
# Themes (provisional)
# ----------------------------

THEMES: List[Dict[str, object]] = [
    {"code": "BOARD_EFFECTIVENESS", "name": "Board effectiveness"},
    {"code": "BOARD_COMPOSITION", "name": "Board composition"},
    {"code": "BOARD_DYNAMICS", "name": "Board dynamics and relationships"},
    {"code": "STRATEGY", "name": "Strategy and business"},
    {"code": "RISK_MONITORING", "name": "Monitoring and risk management"},
    {"code": "AUDIT_ASSURANCE", "name": "Audit and assurance"},
    {"code": "REMUNERATION_NOMINATION", "name": "Remuneration and nomination"},
    {"code": "STAKEHOLDER", "name": "Stakeholder governance"},
    {"code": "COMPLIANCE_ETHICS", "name": "Compliance and ethics"},
    {"code": "MANAGEMENT_OVERSIGHT", "name": "Management oversight"},
    {"code": "INDEPENDENCE", "name": "Independence"},
    {"code": "GENERAL", "name": "General / open comments"},
]

# ----------------------------
# Evidence sources
# ----------------------------

EVIDENCE_SOURCES: List[Dict[str, object]] = [
    {"code": "PERCEPTION", "name": "Perception", "description": "A participant's view of others (peer, whole-board views)."},
    {"code": "ROLE_SELF", "name": "Role self-evidence", "description": "A participant's evidence about their own role."},
    {"code": "ORG_FACT", "name": "Organisational fact", "description": "An organisational or process fact (e.g. from the secretariat)."},
]

SUBJECT_TYPE_CODES = [s["code"] for s in SUBJECT_TYPES]
THEME_CODES = [t["code"] for t in THEMES]
EVIDENCE_SOURCE_CODES = [e["code"] for e in EVIDENCE_SOURCES]
SUBJECT_TYPE_CARDINALITY: Dict[str, str] = {str(s["code"]): str(s["cardinality"]) for s in SUBJECT_TYPES}
