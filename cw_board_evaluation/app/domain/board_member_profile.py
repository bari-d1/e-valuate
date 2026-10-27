"""
app.domain.board_member_profile
-------------------------------
Registry of board member profile facts, in the same style as
app.domain.org_profile: which keys exist, how they are labelled and grouped,
and what shape their value has, so the UI can render a form from it and the
API can validate values.

Value types:
- choice:   one of `options` (governance_role)
- date:     an ISO date, YYYY-MM-DD
- text:     a string
- list:     a list of strings
- tristate: {"answer": "yes" | "no" | "unknown", "detail": optional string}

Rules carried by the registry, for later code to enforce:
- `generation_only`: may shape question wording/tone, must never reach
  analysis (personality_notes).
- Independence facts default to "unknown" when no confirmed fact exists.
  Unknown is a valid, honest state, not an error.
- Tenure against the 9-year limit is calculated from board_appointment_date
  (tenure_years / tenure_status), never stored.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from app.domain.org_profile import FACT_SOURCE_LABELS, FACT_SOURCES, FactValueError
from app.domain.taxonomy import ROLE_TO_SUBJECT_TYPE

# ----------------------------
# Governance roles
# ----------------------------

GOVERNANCE_ROLES: List[Dict[str, str]] = [
    {"key": "chair", "label": "Chair"},
    {"key": "md_ceo", "label": "Managing Director / CEO"},
    {"key": "ed", "label": "Executive director"},
    {"key": "ned", "label": "Non-executive director"},
    {"key": "ined", "label": "Independent non-executive director"},
    {"key": "company_secretary", "label": "Company secretary"},
]
GOVERNANCE_ROLE_KEYS = [r["key"] for r in GOVERNANCE_ROLES]

# Participant.role values written when a governance_role is confirmed. These are
# the spellings already used in the data (and accepted by ROLE_TO_SUBJECT_TYPE).
PARTICIPANT_ROLE_FOR = {
    "chair": "Chair",
    "md_ceo": "MD_CEO",
    "ed": "ED",
    "ned": "NED",
    "ined": "INED",
    "company_secretary": "Company Secretary",
}

# Participant.role (free text) -> governance_role, via the taxonomy's role map
_SUBJECT_TYPE_TO_ROLE = {
    "CHAIR": "chair", "MD_CEO": "md_ceo", "ED": "ed", "NED": "ned", "INED": "ined",
    "COMPANY_SECRETARY": "company_secretary",
}


def governance_role_from_participant_role(role: Optional[str]) -> Optional[str]:
    """governance_role key for a free-text Participant.role, or None if it doesn't map."""
    code = ROLE_TO_SUBJECT_TYPE.get((role or "").strip().lower())
    return _SUBJECT_TYPE_TO_ROLE.get(code) if code else None


# ----------------------------
# Registry
# ----------------------------

TRISTATE_ANSWERS = ("yes", "no", "unknown")

PROFILE_GROUPS: List[Dict[str, Any]] = [
    {"key": "role", "label": "Role"},
    {"key": "background", "label": "Background"},
    {"key": "independence", "label": "Independence",
     "help": "Relevant to independent non-executive directors (also shown for NEDs). "
             "Answer yes or no only from an explicit statement; otherwise it stays unknown.",
     "show_for_roles": ["ined", "ned"], "expanded_for_roles": ["ined"]},
    {"key": "framing", "label": "Framing notes",
     "help": "These set question tone only and are never used in analysis."},
]

INDEPENDENCE_FACTS: List[Dict[str, Any]] = [
    {"key": "holds_company_shares", "label": "Holds shares in the company"},
    {"key": "represents_significant_shareholder", "label": "Represents a significant shareholder"},
    {"key": "employee_of_company_or_group_last_5y", "label": "Employee of the company or group in the last 5 years"},
    {"key": "close_family_tie_to_director_adviser_or_auditor",
     "label": "Close family tie to a director, adviser or auditor"},
    {"key": "material_business_relationship_last_5y", "label": "Material business relationship in the last 5 years"},
    {"key": "senior_service_with_regulator", "label": "Senior service with a regulator"},
    {"key": "provides_advisory_services", "label": "Provides advisory services to the company"},
    {"key": "participates_in_share_or_incentive_scheme", "label": "Participates in a share or incentive scheme"},
]

PROFILE_REGISTRY: List[Dict[str, Any]] = [
    {"key": "governance_role", "label": "Governance role", "type": "choice", "group": "role",
     "options": GOVERNANCE_ROLES, "help": "Their role on this board."},
    {"key": "board_appointment_date", "label": "Board appointment date", "type": "date", "group": "role",
     "help": "Tenure against the 9-year limit is calculated from this."},
    {"key": "other_governance_responsibilities", "label": "Other governance responsibilities", "type": "text",
     "group": "role", "help": "e.g. senior independent director, lead for a specific area."},
    {"key": "qualifications", "label": "Qualifications", "type": "list", "group": "background"},
    {"key": "prior_roles", "label": "Prior roles", "type": "list", "group": "background"},
    {"key": "expertise", "label": "Expertise", "type": "list", "group": "background"},
    {"key": "other_board_roles", "label": "Other board roles", "type": "list", "group": "background"},
    *[{**f, "type": "tristate", "group": "independence", "default": {"answer": "unknown"}} for f in INDEPENDENCE_FACTS],
    {"key": "personality_notes", "label": "Personality and style notes", "type": "text", "group": "framing",
     "generation_only": True,
     "help": "Only what a document literally says about their style. Sets question tone only; never used in analysis."},
]

PROFILE_FACTS_BY_KEY: Dict[str, Dict[str, Any]] = {f["key"]: f for f in PROFILE_REGISTRY}
INDEPENDENCE_KEYS = [f["key"] for f in INDEPENDENCE_FACTS]
GENERATION_ONLY_KEYS = frozenset(f["key"] for f in PROFILE_REGISTRY if f.get("generation_only"))

NINE_YEAR_LIMIT = 9


# ----------------------------
# Validation
# ----------------------------

def validate_profile_value(key: str, value: Any) -> Any:
    """Return the value normalised to the key's type, or raise FactValueError."""
    spec = PROFILE_FACTS_BY_KEY.get(key)
    if spec is None:
        raise FactValueError(f"Unknown profile fact: {key}")
    label, t = spec["label"], spec["type"]

    if value is None:
        raise FactValueError(f"{label} needs a value.")

    if t == "choice":
        v = str(value).strip().lower()
        allowed = [o["key"] for o in spec["options"]]
        if v not in allowed:
            raise FactValueError(f"{label} must be one of: {', '.join(allowed)}.")
        return v

    if t == "date":
        try:
            d = date.fromisoformat(str(value).strip()[:10])
        except ValueError:
            raise FactValueError(f"{label} must be a date (YYYY-MM-DD).")
        if d > date.today():
            raise FactValueError(f"{label} can't be in the future.")
        return d.isoformat()

    if t == "text":
        if not isinstance(value, str) or not value.strip():
            raise FactValueError(f"{label} must be non-empty text.")
        return value.strip()

    if t == "list":
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise FactValueError(f"{label} must be a list of text items.")
        items: List[str] = []
        for x in value:
            x = x.strip()
            if x and x not in items:
                items.append(x)
        if not items:
            raise FactValueError(f"{label} needs at least one item.")
        return items

    if t == "tristate":
        if isinstance(value, str):
            value = {"answer": value}
        if not isinstance(value, dict):
            raise FactValueError(f"{label} must be yes, no or unknown.")
        answer = str(value.get("answer", "")).strip().lower()
        if answer not in TRISTATE_ANSWERS:
            raise FactValueError(f"{label} must be yes, no or unknown.")
        out = {"answer": answer}
        detail = value.get("detail")
        if detail is not None:
            if not isinstance(detail, str):
                raise FactValueError(f"{label}: detail must be text.")
            if detail.strip():
                out["detail"] = detail.strip()
        unknown = set(value) - {"answer", "detail"}
        if unknown:
            raise FactValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}.")
        return out

    raise FactValueError(f"Unsupported value type for {key}: {t}")  # pragma: no cover


# ----------------------------
# Derived values (not stored)
# ----------------------------

def effective_independence(confirmed: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Each independence fact's confirmed value, or {"answer": "unknown"} when there is none."""
    return {k: (confirmed.get(k) or {"answer": "unknown"}) for k in INDEPENDENCE_KEYS}


def all_independence_unknown(confirmed: Dict[str, Any]) -> bool:
    return all(v.get("answer") == "unknown" for v in effective_independence(confirmed).values())


def tenure_years(appointment: Optional[str], as_of: Optional[date] = None) -> Optional[float]:
    """Years on the board since the appointment date (one decimal), or None if unknown."""
    if not appointment:
        return None
    start = date.fromisoformat(appointment)
    end = as_of or date.today()
    if end < start:
        return 0.0
    return round((end - start).days / 365.25, 1)


def tenure_status(appointment: Optional[str], as_of: Optional[date] = None) -> Dict[str, Any]:
    """Tenure against the 9-year limit: years, whether the limit is exceeded, and years remaining."""
    years = tenure_years(appointment, as_of)
    if years is None:
        return {"years": None, "limit_years": NINE_YEAR_LIMIT, "exceeds_limit": None, "years_remaining": None}
    return {
        "years": years,
        "limit_years": NINE_YEAR_LIMIT,
        "exceeds_limit": years > NINE_YEAR_LIMIT,
        "years_remaining": round(max(0.0, NINE_YEAR_LIMIT - years), 1),
    }


def split_generation_only(facts: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Separate facts usable in analysis from generation_only ones (by fact['key'])."""
    usable, generation_only = [], []
    for f in facts:
        (generation_only if f.get("key") in GENERATION_ONLY_KEYS else usable).append(f)
    return {"facts": usable, "generation_only_facts": generation_only}


def registry_for_ui() -> Dict[str, Any]:
    return {
        "groups": PROFILE_GROUPS,
        "facts": PROFILE_REGISTRY,
        "sources": [{"key": k, "label": FACT_SOURCE_LABELS[k]} for k in FACT_SOURCES],
        "governance_roles": GOVERNANCE_ROLES,
        "nine_year_limit": NINE_YEAR_LIMIT,
    }
