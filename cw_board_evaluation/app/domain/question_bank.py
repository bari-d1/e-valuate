"""
app.domain.question_bank
------------------------
Vocabulary and validation for question bank items: the firm's approved
methodology held as data. Each item says what it asks (text, answer type),
what it is about (subject types, binding), who answers it (respondent rule),
when it applies (activation rule), and whether the system already knows the
answer (known_from).

Subject binding decides which subject instances an item repeats over:
- none:                   one instance: the board, or the company secretariat as a function
- self:                   the respondent themselves (their own role must be one of the subject types)
- each_subject_instance:  every person (or committee) in the evaluation of the item's subject types
- respondent_committees:  every committee the respondent sits on

Pure: no database access. Tag codes (themes, evidence sources) are checked
against the database by the service.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.domain.question_rules import fact_scope, validate_rule
from app.domain.taxonomy import SUBJECT_TYPE_CODES

STATUSES = ("draft", "approved", "retired")
ANSWER_TYPES = ("rating", "yesno", "comment", "single_select", "multi_select")
SELECT_TYPES = ("single_select", "multi_select")
SUBJECT_BINDINGS = ("none", "self", "each_subject_instance", "respondent_committees")
KNOWN_FROM_BEHAVIOURS = ("skip", "confirm")
TAG_STATUSES = ("suggested", "confirmed")
CLAUSE_LINK_STATUSES = ("suggested", "confirmed")

# Subject types a binding can produce
PERSON_SUBJECT_TYPES = ("CHAIR", "MD_CEO", "ED", "NED", "INED", "COMPANY_SECRETARY")
NONE_BINDING_SUBJECT_TYPES = ("BOARD", "COMPANY_SECRETARY")

# Rough answering time, for preview estimates
SECONDS_PER_ANSWER = {"rating": 20, "yesno": 10, "single_select": 20, "multi_select": 30, "comment": 90}
SECONDS_TO_CONFIRM = 10

# The two 1-5 scales the historical forms' wording maps onto
SCALES: Dict[str, Dict[str, Any]] = {
    "quality_5": {"min": 1, "max": 5, "labels": {"1": "Poor", "2": "Average", "3": "Good", "4": "Very good", "5": "Excellent"}},
    "agree_5": {"min": 1, "max": 5, "labels": {"1": "Strongly disagree", "2": "Disagree", "3": "Neutral", "4": "Agree",
                                               "5": "Strongly agree"}},
}

CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*-\d{2,3}$")
PLACEHOLDER_PATTERN = re.compile(r"\{([a-z_][a-z0-9_.]*)\}")


class BankItemError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def text_placeholders(text: str) -> List[str]:
    out: List[str] = []
    for k in PLACEHOLDER_PATTERN.findall(text or ""):
        if k not in out:
            out.append(k)
    return out


def fill_placeholders(text: str, values: Dict[str, str]) -> str:
    return PLACEHOLDER_PATTERN.sub(lambda m: values.get(m.group(1), m.group(0)), text or "")


def _str_list(v: Any) -> Optional[List[str]]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        return None
    return [x.strip() for x in v]


def _check_scale(scale: Any, errors: List[str]) -> Optional[Dict[str, Any]]:
    if not isinstance(scale, dict):
        errors.append('Rating items need a scale, e.g. {"min": 1, "max": 5, "labels": {"1": "Poor", ...}}.')
        return None
    lo, hi = scale.get("min"), scale.get("max")
    if not (isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and 0 <= lo < hi <= 10):
        errors.append("Scale min and max must be whole numbers with min < max (at most 10).")
        return None
    labels = scale.get("labels") or {}
    if not isinstance(labels, dict) or not all(isinstance(v, str) and v.strip() for v in labels.values()):
        errors.append("Scale labels must map scale points to text.")
        return None
    bad = [k for k in labels if not (str(k).isdigit() and lo <= int(k) <= hi)]
    if bad:
        errors.append(f"Scale labels outside {lo}-{hi}: {', '.join(map(str, bad))}.")
    out = {"min": lo, "max": hi, "labels": {str(k): v.strip() for k, v in labels.items()}}
    if scale.get("dont_know"):
        out["dont_know"] = True
    unknown = set(scale) - {"min", "max", "labels", "dont_know"}
    if unknown:
        errors.append(f"Scale has unknown fields: {', '.join(sorted(unknown))}.")
    return out


def validate_item(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check and normalise an item's content (everything but tag codes, which need
    the database). Raises BankItemError listing every problem.
    """
    errors: List[str] = []
    out: Dict[str, Any] = {}

    code = str(data.get("code") or "").strip().upper()
    if not CODE_PATTERN.match(code):
        errors.append("Code must look like BOARD-EFF-01 (capitals and digits in parts, ending in a 2-3 digit number).")
    out["code"] = code

    text = str(data.get("text") or "").strip()
    if not text:
        errors.append("Text is required.")
    out["text"] = text

    answer_type = data.get("answer_type")
    if answer_type not in ANSWER_TYPES:
        errors.append(f"Answer type must be one of: {', '.join(ANSWER_TYPES)}.")
    out["answer_type"] = answer_type

    options = data.get("options")
    if answer_type in SELECT_TYPES:
        opts = _str_list(options)
        if opts is None or len([o for o in opts if o]) < 2:
            errors.append("Select items need at least two options (a list of text).")
        else:
            opts = [o for o in opts if o]
            if len(set(o.lower() for o in opts)) != len(opts):
                errors.append("Options must be different from each other.")
            out["options"] = opts
    elif options:
        errors.append(f"Only select items have options ({answer_type} items don't).")
    out.setdefault("options", None)

    if answer_type == "rating":
        out["scale"] = _check_scale(data.get("scale"), errors)
    else:
        if data.get("scale"):
            errors.append("Only rating items have a scale.")
        out["scale"] = None

    subject_types = data.get("subject_types")
    st = _str_list(subject_types)
    if not st:
        errors.append("At least one subject type is required.")
        st = []
    else:
        bad = [s for s in st if s not in SUBJECT_TYPE_CODES]
        if bad:
            errors.append(f"Unknown subject types: {', '.join(bad)}.")
    out["subject_types"] = list(dict.fromkeys(st))

    binding = data.get("subject_binding")
    if binding not in SUBJECT_BINDINGS:
        errors.append(f"Subject binding must be one of: {', '.join(SUBJECT_BINDINGS)}.")
    elif binding == "none" and not set(st) <= set(NONE_BINDING_SUBJECT_TYPES):
        errors.append("Binding 'none' is for items about the board or the company secretariat only; "
                      "use each_subject_instance or self for people.")
    elif binding == "self" and not set(st) <= set(PERSON_SUBJECT_TYPES):
        errors.append("Binding 'self' needs person subject types (CHAIR, MD_CEO, ED, NED, INED, COMPANY_SECRETARY).")
    elif binding == "respondent_committees" and st != ["COMMITTEE"]:
        errors.append("Binding 'respondent_committees' needs the subject type COMMITTEE only.")
    out["subject_binding"] = binding

    for key in ("respondent_rule", "activation_rule"):
        rule = data.get(key)
        problems = validate_rule(rule)
        label = "Respondent rule" if key == "respondent_rule" else "Activation rule"
        errors.extend(f"{label}: {p}" for p in problems)
        out[key] = rule or None

    known_from = (data.get("known_from") or "").strip() or None
    if known_from and not fact_scope(known_from):
        errors.append(f"known_from: unknown fact key {known_from!r}.")
    out["known_from"] = known_from
    behaviour = data.get("known_from_behaviour") or "skip"
    if behaviour not in KNOWN_FROM_BEHAVIOURS:
        errors.append(f"known_from_behaviour must be one of: {', '.join(KNOWN_FROM_BEHAVIOURS)}.")
    out["known_from_behaviour"] = behaviour

    placeholders = data.get("placeholders") or []
    ph = _str_list(placeholders)
    if ph is None:
        errors.append("Placeholders must be a list of fact keys.")
        ph = []
    bad = [p for p in ph if not fact_scope(p)]
    if bad:
        errors.append(f"Unknown placeholder fact keys: {', '.join(bad)}.")
    in_text = text_placeholders(text) + [p for o in (out.get("options") or []) for p in text_placeholders(o)]
    missing = [p for p in in_text if p not in ph]
    unused = [p for p in ph if p not in in_text]
    if missing:
        errors.append(f"Text uses placeholders not listed in placeholders: {', '.join(missing)}.")
    if unused:
        errors.append(f"Placeholders listed but not used in the text: {', '.join(unused)}.")
    out["placeholders"] = list(dict.fromkeys(ph))

    weight = data.get("weight", 1)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight < 0:
        errors.append("Weight must be a number >= 0.")
    out["weight"] = weight

    sort_order = data.get("sort_order", 0)
    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        errors.append("Sort order must be a whole number.")
    out["sort_order"] = sort_order

    source_refs = data.get("source_refs") or []
    if not isinstance(source_refs, list) or not all(isinstance(r, dict) for r in source_refs):
        errors.append("Source references must be a list of objects.")
        source_refs = []
    out["source_refs"] = source_refs

    tag_notes = data.get("tag_notes") or {}
    if not isinstance(tag_notes, dict):
        errors.append("tag_notes must be an object.")
        tag_notes = {}
    for k, v in tag_notes.items():
        if not isinstance(v, dict) or v.get("status") not in TAG_STATUSES:
            errors.append(f"tag_notes.{k} needs a status of suggested or confirmed.")
    out["tag_notes"] = tag_notes

    for key in ("guidance", "review_notes"):
        v = data.get(key)
        out[key] = v.strip() if isinstance(v, str) and v.strip() else None

    if errors:
        raise BankItemError(errors)
    return out


def estimate_seconds(answer_type: str, confirm: bool = False) -> int:
    return SECONDS_TO_CONFIRM if confirm else SECONDS_PER_ANSWER.get(answer_type, 30)
