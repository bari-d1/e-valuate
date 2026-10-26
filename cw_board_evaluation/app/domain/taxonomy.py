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

from dataclasses import dataclass
from typing import Dict, List, Optional

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

# ----------------------------
# Legacy Question.dimension -> theme (used once, by the backfill migration)
# ----------------------------

DIMENSION_TO_THEME: Dict[str, str] = {
    "Board Composition": "BOARD_COMPOSITION",
    "Risk Oversight": "RISK_MONITORING",
    "Strategy Oversight": "STRATEGY",
    "Board Culture & Dynamics": "BOARD_DYNAMICS",
    "Audit & Assurance": "AUDIT_ASSURANCE",
    "Remuneration & Nomination": "REMUNERATION_NOMINATION",
    "Stakeholder & Stakeholder Governance": "STAKEHOLDER",
    "Compliance & Ethics": "COMPLIANCE_ETHICS",
    "Management Oversight": "MANAGEMENT_OVERSIGHT",
    "Open Comments": "GENERAL",
}

# ----------------------------
# Participant.role -> subject type
# ----------------------------

# Participant.role is free text. These are the values found in code, seed data,
# tests and the demo database ("Chair", "INED", "ED", "Company Secretary"), plus
# the subject type codes themselves. Matching is trimmed and case-insensitive.
# Anything else (including "Chairman", "CEO", "MD", "NED-I") is deliberately
# unmapped: callers report it instead of guessing. Extend this table as roles
# are confirmed.
ROLE_TO_SUBJECT_TYPE: Dict[str, str] = {
    "chair": "CHAIR",
    "ined": "INED",
    "ed": "ED",
    "company secretary": "COMPANY_SECRETARY",
    "ned": "NED",
    "md_ceo": "MD_CEO",
    "company_secretary": "COMPANY_SECRETARY",
}

DIRECTOR_SUBJECT_TYPES = ("NED", "INED", "ED")


def subject_type_for_role(role: Optional[str]) -> Optional[str]:
    """Subject type code for a Participant.role, or None when unknown/empty."""
    key = (role or "").strip().lower()
    if not key:
        return None
    return ROLE_TO_SUBJECT_TYPE.get(key)


# ----------------------------
# Legacy assignment type -> subject type
# ----------------------------

@dataclass(frozen=True)
class AssignmentMapping:
    subject_type_code: Optional[str]  # None when it can't be resolved
    theme_code: Optional[str] = None
    provisional: bool = False
    reason: Optional[str] = None  # why subject_type_code is None


# Fixed mappings. DIRECTOR_SELF / DIRECTOR_PEER are absent on purpose: they
# depend on the subject participant's role (see map_assignment_type).
ASSIGNMENT_TYPE_TO_SUBJECT_TYPE: Dict[str, str] = {
    "BOARD_AS_WHOLE": "BOARD",
    "CHAIR_EVAL": "CHAIR",
    "CEO_SELF": "MD_CEO",
    "CEO_EVAL": "MD_CEO",
    "ED_SELF": "ED",
    "ED_EVAL": "ED",
    "COMMITTEE_EVAL": "COMMITTEE",
    # PROVISIONAL: the client hasn't confirmed whether governance compliance is
    # a subject or a theme. Treated as the board, themed COMPLIANCE_ETHICS.
    "GOV_AUDIT": "BOARD",
}

ASSIGNMENT_TYPE_THEME: Dict[str, str] = {
    "GOV_AUDIT": "COMPLIANCE_ETHICS",  # PROVISIONAL, see above
}

PROVISIONAL_ASSIGNMENT_TYPES = frozenset({"GOV_AUDIT"})

ROLE_RESOLVED_ASSIGNMENT_TYPES = frozenset({"DIRECTOR_SELF", "DIRECTOR_PEER"})

LEGACY_ASSIGNMENT_TYPES = tuple(ASSIGNMENT_TYPE_TO_SUBJECT_TYPE) + tuple(sorted(ROLE_RESOLVED_ASSIGNMENT_TYPES))


def map_assignment_type(assignment_type: str, subject_role: Optional[str] = None) -> AssignmentMapping:
    """
    Map a legacy AssessmentAssignment.assignment_type to a subject type.

    subject_role is the role of the assignment's subject participant; it is only
    used for DIRECTOR_SELF / DIRECTOR_PEER, which resolve to NED, INED or ED.
    """
    atype = (assignment_type or "").strip().upper()

    if atype in ROLE_RESOLVED_ASSIGNMENT_TYPES:
        code = subject_type_for_role(subject_role)
        if code in DIRECTOR_SUBJECT_TYPES:
            return AssignmentMapping(subject_type_code=code)
        return AssignmentMapping(
            subject_type_code=None,
            reason=f"{atype} needs a subject participant with role NED, INED or ED (got {subject_role!r}).",
        )

    if atype in ASSIGNMENT_TYPE_TO_SUBJECT_TYPE:
        return AssignmentMapping(
            subject_type_code=ASSIGNMENT_TYPE_TO_SUBJECT_TYPE[atype],
            theme_code=ASSIGNMENT_TYPE_THEME.get(atype),
            provisional=atype in PROVISIONAL_ASSIGNMENT_TYPES,
        )

    return AssignmentMapping(subject_type_code=None, reason=f"Unknown assignment type {assignment_type!r}.")
