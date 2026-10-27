"""
app.domain.org_profile
----------------------
Registry of organisation profile facts. The single source of truth for which
keys exist, how they are labelled and grouped, and what shape their value has,
so the UI can render a form from it and the API can validate values.

Value types:
- text:    a string
- number:  a whole number >= 0
- list:    a list of strings
- object:  a dict with the fields listed in `fields` (each a whole number >= 0)
"""

from __future__ import annotations

from typing import Any, Dict, List

FACT_SOURCES = ("public", "client", "consultant")
FACT_SOURCE_LABELS = {"public": "Public", "client": "Client", "consultant": "Consultant"}

DOC_TYPES: List[Dict[str, str]] = [
    {"key": "company_profile", "label": "Company profile"},
    {"key": "board_structure", "label": "Board structure"},
    {"key": "committee_tor", "label": "Committee terms of reference"},
    {"key": "governance_policy", "label": "Governance policies"},
    {"key": "annual_report", "label": "Annual report"},
    {"key": "public_info", "label": "Public information"},
    {"key": "other", "label": "Other"},
]
DOC_TYPE_KEYS = [d["key"] for d in DOC_TYPES]

COMMITTEE_TYPES = ("audit", "risk", "remuneration", "nomination", "finance", "governance", "other")

FACT_GROUPS: List[Dict[str, str]] = [
    {"key": "organisation", "label": "Organisation"},
    {"key": "regulation", "label": "Regulation"},
    {"key": "board", "label": "Board"},
    {"key": "context", "label": "Context"},
]

BOARD_COMPOSITION_FIELDS = [
    {"key": "executive_directors", "label": "Executive directors"},
    {"key": "non_executive_directors", "label": "Non-executive directors"},
    {"key": "independent_non_executive_directors", "label": "Independent non-executive directors"},
    {"key": "women", "label": "Women"},
    {"key": "men", "label": "Men"},
]

FACT_REGISTRY: List[Dict[str, Any]] = [
    {"key": "listing_status", "label": "Listing status", "type": "text", "group": "organisation",
     "help": "e.g. Listed on the Nigerian Exchange; unlisted public company; private company."},
    {"key": "ownership", "label": "Ownership", "type": "text", "group": "organisation",
     "help": "Major shareholders or group structure, as stated."},
    {"key": "years_in_operation", "label": "Years in operation", "type": "number", "group": "organisation",
     "help": "Only if a document states it."},
    {"key": "organisation_size", "label": "Organisation size", "type": "text", "group": "organisation",
     "help": "e.g. number of employees or branches, as stated."},
    {"key": "regulator", "label": "Regulators", "type": "list", "group": "regulation",
     "help": "Regulators named in the documents, e.g. NAICOM, CBN."},
    {"key": "board_size", "label": "Board size", "type": "number", "group": "board",
     "help": "Number of directors actually on the board, as stated (not the minimum or maximum a charter allows)."},
    {"key": "board_composition", "label": "Board composition", "type": "object", "group": "board",
     "fields": BOARD_COMPOSITION_FIELDS,
     "help": "Counts of executive, non-executive and independent directors, and gender mix."},
    {"key": "recent_events", "label": "Recent events", "type": "list", "group": "context",
     "help": "Events in or near the review period, one short item each: e.g. mergers and acquisitions, leadership changes, regulatory actions or fines, capital raises."},
    {"key": "strategic_context", "label": "Strategic context", "type": "text", "group": "context",
     "help": "Strategy and business priorities, as stated."},
    {"key": "governance_context", "label": "Governance context", "type": "text", "group": "context",
     "help": "Governance arrangements or issues, as stated."},
]

FACTS_BY_KEY: Dict[str, Dict[str, Any]] = {f["key"]: f for f in FACT_REGISTRY}


class FactValueError(ValueError):
    pass


def _whole_number(v: Any, what: str) -> int:
    if isinstance(v, bool):
        raise FactValueError(f"{what} must be a whole number.")
    if isinstance(v, int):
        n = v
    elif isinstance(v, float) and v.is_integer():
        n = int(v)
    elif isinstance(v, str) and v.strip().isdigit():
        n = int(v.strip())
    else:
        raise FactValueError(f"{what} must be a whole number.")
    if n < 0:
        raise FactValueError(f"{what} can't be negative.")
    return n


def validate_fact_value(key: str, value: Any) -> Any:
    """Return the value normalised to the key's type, or raise FactValueError."""
    spec = FACTS_BY_KEY.get(key)
    if spec is None:
        raise FactValueError(f"Unknown fact key: {key}")
    label = spec["label"]
    t = spec["type"]

    if value is None:
        raise FactValueError(f"{label} needs a value.")

    if t == "text":
        if not isinstance(value, str) or not value.strip():
            raise FactValueError(f"{label} must be non-empty text.")
        return value.strip()

    if t == "number":
        return _whole_number(value, label)

    if t == "list":
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise FactValueError(f"{label} must be a list of text items.")
        items = []
        for item in value:
            if not isinstance(item, str):
                raise FactValueError(f"{label} must be a list of text items.")
            item = item.strip()
            if item and item not in items:
                items.append(item)
        if not items:
            raise FactValueError(f"{label} needs at least one item.")
        return items

    if t == "object":
        if not isinstance(value, dict):
            raise FactValueError(f"{label} must be an object.")
        allowed = {f["key"] for f in spec["fields"]}
        unknown = set(value) - allowed
        if unknown:
            raise FactValueError(f"{label} has unknown fields: {', '.join(sorted(unknown))}.")
        out = {k: _whole_number(v, f"{label}: {k}") for k, v in value.items() if v is not None}
        if not out:
            raise FactValueError(f"{label} needs at least one count.")
        return out

    raise FactValueError(f"Unsupported value type for {key}: {t}")  # pragma: no cover


def registry_for_ui() -> Dict[str, Any]:
    return {
        "groups": FACT_GROUPS,
        "facts": FACT_REGISTRY,
        "sources": [{"key": k, "label": FACT_SOURCE_LABELS[k]} for k in FACT_SOURCES],
        "doc_types": DOC_TYPES,
        "committee_types": list(COMMITTEE_TYPES),
    }
