"""
app.domain.question_rules
-------------------------
The rule language that decides which question bank items a participant gets,
and about which subject. Small, deterministic and JSON-shaped so consultants
can read and edit rules, and so every decision comes with reasons.

A rule is null/{} (always true), a combinator or a condition:

    {"all": [rule, ...]}      every rule is true
    {"any": [rule, ...]}      at least one rule is true
    {"not": rule}             the rule is false
    {"<condition>": argument} a single condition (an object with exactly one key)

Conditions (see CONDITIONS for the argument each takes):

    respondent.role                         ["chair", "ined", ...]   governance role keys
    respondent.is_subject                   true
    respondent.is_not_subject               true
    respondent.is_member_of_subject_committee true
    respondent.chairs_subject_committee     true
    subject.type                            ["BOARD", "NED", ...]    subject type codes
    subject.committee_type                  ["audit", ...]           committee types
    subject.committee_name_contains         ["statutory", ...]       case-insensitive
    org.sector                              ["insurance", ...]       sector keys
    org.has_code                            "NAICOM_2021"
    evaluation.scope_includes               "INED"
    evaluation.option                       {"key": "peer_mode", "value": "core"}
    fact.known                              "<fact key>"
    fact.unknown                            "<fact key>"
    fact.at_least / fact.at_most            {"key": "<fact key>", "value": 2}

Results are three-valued: True, False, or None when the data needed to decide
is missing (e.g. the respondent's role isn't confirmed). None is reported as
"blocked by missing data", never treated as false.

Everything here is pure: callers pass a context dict (see `evaluate`) built
from the database elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.domain.board_member_profile import GOVERNANCE_ROLE_KEYS, PROFILE_FACTS_BY_KEY
from app.domain.evaluation_options import OPTIONS_BY_KEY, effective_options, option_values
from app.domain.governance import GOVERNANCE_CODE_KEYS, SECTOR_KEYS
from app.domain.org_profile import COMMITTEE_TYPES, FACTS_BY_KEY
from app.domain.taxonomy import SUBJECT_TYPE_CODES, SUBJECT_TYPES


class RuleError(ValueError):
    """A rule failed validation. `errors` lists every problem found."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


# ----------------------------
# Fact keys usable in rules, known_from and placeholders
# ----------------------------

# Derived values the selection service adds to the context (never stored)
DERIVED_PERSON_FACTS = {
    "tenure_years": "Years on the board (from the appointment date)",
    "committee_types": "Types of the committees they sit on",
}
DERIVED_COMMITTEE_FACTS = {"committee_member_count": "Number of committee members"}
EVALUATION_FACTS = {"review_year": "Year under review"}


def _org_fact_keys() -> Dict[str, str]:
    keys: Dict[str, str] = {}
    for k, spec in FACTS_BY_KEY.items():
        keys[k] = spec["label"]
        for f in spec.get("fields", []):
            keys[f"{k}.{f['key']}"] = f"{spec['label']}: {f['label']}"
    return keys


ORG_FACT_KEYS = _org_fact_keys()
PERSON_FACT_KEYS = {**{k: s["label"] for k, s in PROFILE_FACTS_BY_KEY.items()}, **DERIVED_PERSON_FACTS}


def fact_scope(key: str) -> Optional[str]:
    """Where a fact key lives: 'org', 'person', 'committee', 'evaluation', or None if unknown."""
    if key in ORG_FACT_KEYS:
        return "org"
    if key in PERSON_FACT_KEYS:
        return "person"
    if key in DERIVED_COMMITTEE_FACTS:
        return "committee"
    if key in EVALUATION_FACTS:
        return "evaluation"
    return None


def fact_label(key: str) -> str:
    return {**ORG_FACT_KEYS, **PERSON_FACT_KEYS, **DERIVED_COMMITTEE_FACTS, **EVALUATION_FACTS}.get(key, key)


def all_fact_keys() -> List[Dict[str, str]]:
    out = []
    for scope, keys in (("org", ORG_FACT_KEYS), ("person", PERSON_FACT_KEYS),
                        ("committee", DERIVED_COMMITTEE_FACTS), ("evaluation", EVALUATION_FACTS)):
        out.extend({"key": k, "label": v, "scope": scope} for k, v in keys.items())
    return out


def _has_value(v: Any) -> bool:
    """A fact counts as known when it has a real value; tristate 'unknown' does not."""
    if v is None:
        return False
    if isinstance(v, dict) and "answer" in v:
        return v.get("answer") in ("yes", "no")
    if isinstance(v, (list, str, dict)):
        return len(v) > 0
    return True


def lookup_fact(ctx: Dict[str, Any], key: str) -> Tuple[bool, Any]:
    """
    (known, value) for a fact key in a selection context. Person facts are read
    from the subject when the subject is a person, otherwise from the respondent.
    """
    scope = fact_scope(key)
    if scope == "org":
        facts = (ctx.get("org") or {}).get("facts") or {}
        base, _, sub = key.partition(".")
        v = facts.get(base)
        if sub:
            v = v.get(sub) if isinstance(v, dict) else None
    elif scope == "person":
        subject = ctx.get("subject") or {}
        owner = subject if subject.get("kind") == "person" else (ctx.get("respondent") or {})
        v = (owner.get("facts") or {}).get(key)
    elif scope == "committee":
        subject = ctx.get("subject") or {}
        v = (subject.get("facts") or {}).get(key) if subject.get("kind") == "committee" else None
    elif scope == "evaluation":
        v = (ctx.get("evaluation") or {}).get(key)
    else:
        return False, None
    return (_has_value(v), v if _has_value(v) else None)


def format_fact_value(v: Any) -> str:
    """A stored fact value as short readable text (for reasons and the preview)."""
    if isinstance(v, dict) and "answer" in v:
        text = {"yes": "Yes", "no": "No"}.get(v.get("answer"), "Unknown")
        return f"{text} ({v['detail']})" if v.get("detail") else text
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k.replace('_', ' ')}: {x}" for k, x in v.items())
    return str(v)


# ----------------------------
# Wording
# ----------------------------

ROLE_PHRASES = {
    "chair": "the chair",
    "md_ceo": "the MD/CEO",
    "ed": "an executive director",
    "ned": "a non-executive director",
    "ined": "an independent NED",
    "company_secretary": "the company secretary",
}
SUBJECT_TYPE_NAMES = {str(s["code"]): str(s["name"]).lower() for s in SUBJECT_TYPES}
SUBJECT_TYPE_NAMES.update({"BOARD": "the board", "CHAIR": "the chair", "MD_CEO": "the MD/CEO",
                           "COMPANY_SECRETARY": "the company secretariat", "INED": "an independent NED",
                           "NED": "a non-executive director", "ED": "an executive director",
                           "COMMITTEE": "a board committee"})


def _or_list(items: List[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " or " + items[-1]


def _code_name(code: str) -> str:
    return code.replace("_", " ")


# ----------------------------
# Conditions
# ----------------------------

@dataclass
class RuleResult:
    value: Optional[bool]  # None: missing data
    reasons: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


def _list_of(allowed: Optional[List[str]], what: str, upper: bool = False) -> Callable[[Any], List[str]]:
    def check(arg: Any) -> List[str]:
        if not isinstance(arg, list) or not arg or not all(isinstance(x, str) and x.strip() for x in arg):
            return [f"needs a non-empty list of {what}"]
        if allowed is not None:
            bad = [x for x in arg if x not in allowed]
            if bad:
                return [f"unknown {what}: {', '.join(bad)} (allowed: {', '.join(allowed)})"]
        return []
    return check


def _one_of(allowed: List[str], what: str) -> Callable[[Any], List[str]]:
    def check(arg: Any) -> List[str]:
        if not isinstance(arg, str) or not arg.strip():
            return [f"needs a {what} as text"]
        if arg not in allowed:
            return [f"unknown {what} {arg!r} (allowed: {', '.join(allowed)})"]
        return []
    return check


def _true_only(arg: Any) -> List[str]:
    return [] if arg is True else ["takes true (write the opposite condition, or wrap it in not, instead of false)"]


def _fact_key(arg: Any) -> List[str]:
    if not isinstance(arg, str) or not arg.strip():
        return ["needs a fact key as text"]
    return [] if fact_scope(arg) else [f"unknown fact key {arg!r}"]


def _fact_compare(arg: Any) -> List[str]:
    if not isinstance(arg, dict) or set(arg) != {"key", "value"}:
        return ['needs {"key": "<fact key>", "value": <number>}']
    errs = _fact_key(arg["key"])
    if isinstance(arg["value"], bool) or not isinstance(arg["value"], (int, float)):
        errs.append("value must be a number")
    return errs


def _respondent_role(arg, ctx) -> RuleResult:
    role = (ctx.get("respondent") or {}).get("role")
    wanted = _or_list([ROLE_PHRASES.get(r, r) for r in arg])
    if not role:
        return RuleResult(None, [f"needs the respondent's governance role (looking for {wanted})"],
                          ["respondent's governance role"])
    phrase = ROLE_PHRASES.get(role, role)
    if role in arg:
        return RuleResult(True, [f"respondent is {phrase}"])
    return RuleResult(False, [f"respondent is {phrase}, not {wanted}"])


def _is_subject(ctx) -> Optional[bool]:
    subject = ctx.get("subject") or {}
    if subject.get("kind") != "person":
        return False
    return bool(subject.get("participant_id")) and subject.get("participant_id") == (ctx.get("respondent") or {}).get("participant_id")


def _respondent_is_subject(arg, ctx) -> RuleResult:
    if _is_subject(ctx):
        return RuleResult(True, ["the item is about themselves"])
    return RuleResult(False, [f"the item is about {(ctx.get('subject') or {}).get('label') or 'someone else'}, not themselves"])


def _respondent_is_not_subject(arg, ctx) -> RuleResult:
    if _is_subject(ctx):
        return RuleResult(False, ["the item would be about themselves"])
    return RuleResult(True, [f"the item is about {(ctx.get('subject') or {}).get('label') or 'someone else'}, not themselves"])


def _respondent_membership(ctx) -> Tuple[Optional[Dict[str, Any]], str]:
    subject = ctx.get("subject") or {}
    name = subject.get("label") or "the committee"
    for c in (ctx.get("respondent") or {}).get("committees") or []:
        if subject.get("committee_id") and c.get("committee_id") == subject.get("committee_id"):
            return c, name
    return None, name


def _member_of_subject_committee(arg, ctx) -> RuleResult:
    if (ctx.get("subject") or {}).get("kind") != "committee":
        return RuleResult(False, ["the item is not about a committee"])
    ms, name = _respondent_membership(ctx)
    if ms:
        return RuleResult(True, [f"respondent sits on {name}"])
    return RuleResult(False, [f"respondent doesn't sit on {name}"])


def _chairs_subject_committee(arg, ctx) -> RuleResult:
    if (ctx.get("subject") or {}).get("kind") != "committee":
        return RuleResult(False, ["the item is not about a committee"])
    ms, name = _respondent_membership(ctx)
    if ms and ms.get("role") == "chair":
        return RuleResult(True, [f"respondent chairs {name}"])
    return RuleResult(False, [f"respondent doesn't chair {name}"])


def _subject_type(arg, ctx) -> RuleResult:
    t = (ctx.get("subject") or {}).get("type")
    phrase = SUBJECT_TYPE_NAMES.get(t, t or "nothing")
    if t in arg:
        return RuleResult(True, [f"the item is about {phrase}"])
    return RuleResult(False, [f"the item is about {phrase}, not {_or_list([SUBJECT_TYPE_NAMES.get(x, x) for x in arg])}"])


def _subject_committee_type(arg, ctx) -> RuleResult:
    subject = ctx.get("subject") or {}
    if subject.get("kind") != "committee":
        return RuleResult(False, ["the item is not about a committee"])
    t = subject.get("committee_type")
    if not t:
        return RuleResult(None, [f"needs the type of {subject.get('label') or 'the committee'}"], ["committee type"])
    if t in arg:
        return RuleResult(True, [f"{subject.get('label')} is a{'n' if t[0] in 'aeiou' else ''} {t} committee"])
    return RuleResult(False, [f"{subject.get('label')} is a{'n' if t[0] in 'aeiou' else ''} {t} committee, not {_or_list(arg)}"])


def _subject_committee_name_contains(arg, ctx) -> RuleResult:
    subject = ctx.get("subject") or {}
    if subject.get("kind") != "committee":
        return RuleResult(False, ["the item is not about a committee"])
    name = subject.get("committee_name") or subject.get("label") or ""
    hit = next((w for w in arg if w.lower() in name.lower()), None)
    if hit:
        return RuleResult(True, [f"the committee name {name!r} contains {hit!r}"])
    return RuleResult(False, [f"the committee name {name!r} doesn't contain {_or_list([repr(w) for w in arg])}"])


def _org_sector(arg, ctx) -> RuleResult:
    sector = (ctx.get("org") or {}).get("sector")
    if not sector:
        return RuleResult(None, ["needs the company's sector"], ["company sector"])
    if sector in arg:
        return RuleResult(True, [f"the company is in the {sector} sector"])
    return RuleResult(False, [f"the company is in the {sector} sector, not {_or_list(arg)}"])


def _org_has_code(arg, ctx) -> RuleResult:
    codes = (ctx.get("org") or {}).get("codes") or []
    if not codes:
        return RuleResult(None, ["needs the governance codes for the evaluation"], ["governance codes"])
    if arg in codes:
        return RuleResult(True, [f"the evaluation is assessed against {_code_name(arg)}"])
    return RuleResult(False, [f"the evaluation isn't assessed against {_code_name(arg)}"])


def _scope_includes(arg, ctx) -> RuleResult:
    scope = (ctx.get("evaluation") or {}).get("scope") or []
    name = SUBJECT_TYPE_NAMES.get(arg, arg)
    if arg in scope:
        return RuleResult(True, [f"the evaluation's scope includes {name}"])
    return RuleResult(False, [f"the evaluation's scope doesn't include {name}"])


def _option_check(arg: Any) -> List[str]:
    if not isinstance(arg, dict) or set(arg) != {"key", "value"}:
        return ['needs {"key": "<option>", "value": "<value>"}']
    if arg["key"] not in OPTIONS_BY_KEY:
        return [f"unknown option {arg['key']!r} (known: {', '.join(OPTIONS_BY_KEY)})"]
    if arg["value"] not in option_values(arg["key"]):
        return [f"{arg['key']} must be one of: {', '.join(option_values(arg['key']))}"]
    return []


def _evaluation_option(arg, ctx) -> RuleResult:
    value = effective_options((ctx.get("evaluation") or {}).get("options"))[arg["key"]]
    if value == arg["value"]:
        return RuleResult(True, [f"the evaluation uses {arg['key'].replace('_', ' ')} {value!r}"])
    return RuleResult(False, [f"the evaluation uses {arg['key'].replace('_', ' ')} {value!r}, not {arg['value']!r}"])


def _fact_known(arg, ctx) -> RuleResult:
    known, v = lookup_fact(ctx, arg)
    if known:
        return RuleResult(True, [f"{fact_label(arg)} is known ({format_fact_value(v)})"])
    return RuleResult(False, [f"{fact_label(arg)} is not known"])


def _fact_unknown(arg, ctx) -> RuleResult:
    known, v = lookup_fact(ctx, arg)
    if known:
        return RuleResult(False, [f"{fact_label(arg)} is already known ({format_fact_value(v)})"])
    return RuleResult(True, [f"{fact_label(arg)} is not known yet"])


def _fact_compare_eval(op: str):
    def run(arg, ctx) -> RuleResult:
        key, limit = arg["key"], arg["value"]
        known, v = lookup_fact(ctx, key)
        label = fact_label(key)
        if not known:
            return RuleResult(None, [f"needs {label}"], [label])
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return RuleResult(False, [f"{label} is not a number ({format_fact_value(v)})"])
        ok = v >= limit if op == "at_least" else v <= limit
        words = "at least" if op == "at_least" else "at most"
        if ok:
            return RuleResult(True, [f"{label} is {v} ({words} {limit})"])
        return RuleResult(False, [f"{label} is {v}, not {words} {limit}"])
    return run


# name -> (argument description, validator, evaluator)
CONDITIONS: Dict[str, Tuple[str, Callable[[Any], List[str]], Callable[[Any, Dict[str, Any]], RuleResult]]] = {
    "respondent.role": ("list of governance roles", _list_of(GOVERNANCE_ROLE_KEYS, "governance roles"), _respondent_role),
    "respondent.is_subject": ("true", _true_only, _respondent_is_subject),
    "respondent.is_not_subject": ("true", _true_only, _respondent_is_not_subject),
    "respondent.is_member_of_subject_committee": ("true", _true_only, _member_of_subject_committee),
    "respondent.chairs_subject_committee": ("true", _true_only, _chairs_subject_committee),
    "subject.type": ("list of subject types", _list_of(SUBJECT_TYPE_CODES, "subject types"), _subject_type),
    "subject.committee_type": ("list of committee types", _list_of(list(COMMITTEE_TYPES), "committee types"), _subject_committee_type),
    "subject.committee_name_contains": ("list of words", _list_of(None, "words"), _subject_committee_name_contains),
    "org.sector": ("list of sectors", _list_of(SECTOR_KEYS, "sectors"), _org_sector),
    "org.has_code": ("governance code", _one_of(GOVERNANCE_CODE_KEYS, "governance code"), _org_has_code),
    "evaluation.scope_includes": ("subject type", _one_of(SUBJECT_TYPE_CODES, "subject type"), _scope_includes),
    "evaluation.option": ('{"key": option, "value": value}', _option_check, _evaluation_option),
    "fact.known": ("fact key", _fact_key, _fact_known),
    "fact.unknown": ("fact key", _fact_key, _fact_unknown),
    "fact.at_least": ('{"key": fact key, "value": number}', _fact_compare, _fact_compare_eval("at_least")),
    "fact.at_most": ('{"key": fact key, "value": number}', _fact_compare, _fact_compare_eval("at_most")),
}
COMBINATORS = ("all", "any", "not")


# ----------------------------
# Validation
# ----------------------------

def _validate(rule: Any, path: str, errors: List[str]) -> None:
    where = path or "rule"
    if not isinstance(rule, dict):
        errors.append(f"{where}: must be an object, e.g. {{\"respondent.role\": [\"chair\"]}}")
        return
    if len(rule) != 1:
        keys = ", ".join(sorted(rule)) or "none"
        errors.append(f"{where}: must have exactly one key (a condition, all, any or not); found {keys}")
        return
    (name, arg), = rule.items()
    if name in ("all", "any"):
        if not isinstance(arg, list) or not arg:
            errors.append(f"{where}.{name}: needs a non-empty list of rules")
            return
        for i, child in enumerate(arg):
            _validate(child, f"{path + '.' if path else ''}{name}[{i}]", errors)
        return
    if name == "not":
        _validate(arg, f"{path + '.' if path else ''}not", errors)
        return
    spec = CONDITIONS.get(name)
    if spec is None:
        errors.append(f"{where}: unknown condition {name!r}. Known conditions: {', '.join(CONDITIONS)}; "
                      f"combinators: {', '.join(COMBINATORS)}")
        return
    errors.extend(f"{where}: {name} {e}" for e in spec[1](arg))


def validate_rule(rule: Any) -> List[str]:
    """Every problem with a rule, as readable messages with their location. [] when valid."""
    if rule is None or rule == {}:
        return []
    errors: List[str] = []
    _validate(rule, "", errors)
    return errors


def ensure_valid_rule(rule: Any) -> Optional[Dict[str, Any]]:
    """The rule (None for empty), or raise RuleError."""
    errors = validate_rule(rule)
    if errors:
        raise RuleError(errors)
    return rule or None


# ----------------------------
# Evaluation
# ----------------------------

def _dedupe(items: List[str]) -> List[str]:
    out: List[str] = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


def _eval(rule: Dict[str, Any], ctx: Dict[str, Any]) -> RuleResult:
    (name, arg), = rule.items()
    if name in ("all", "any"):
        results = [_eval(r, ctx) for r in arg]
        trues = [r for r in results if r.value is True]
        falses = [r for r in results if r.value is False]
        nones = [r for r in results if r.value is None]
        if name == "all":
            if falses:
                return RuleResult(False, _dedupe([x for r in falses for x in r.reasons]))
            if nones:
                return RuleResult(None, _dedupe([x for r in nones for x in r.reasons]),
                                  _dedupe([x for r in nones for x in r.missing]))
            return RuleResult(True, _dedupe([x for r in trues for x in r.reasons]))
        if trues:
            return RuleResult(True, list(trues[0].reasons))
        if nones:
            return RuleResult(None, _dedupe([x for r in nones for x in r.reasons]),
                              _dedupe([x for r in nones for x in r.missing]))
        return RuleResult(False, _dedupe([x for r in falses for x in r.reasons]))
    if name == "not":
        r = _eval(arg, ctx)
        return RuleResult(None if r.value is None else not r.value, r.reasons, r.missing)
    return CONDITIONS[name][2](arg, ctx)


def evaluate(rule: Any, ctx: Dict[str, Any]) -> RuleResult:
    """
    Evaluate a (valid) rule against a context:

        {"respondent": {"participant_id", "label", "role", "committees": [{"committee_id", "role"}], "facts"},
         "subject":    {"kind": "board"|"function"|"person"|"committee", "type", "label",
                        "participant_id", "committee_id", "committee_type", "committee_name", "facts"},
         "org":        {"sector", "codes", "facts"},
         "evaluation": {"scope", "review_year", "options"}}

    Returns the result (True / False / None for missing data) with reasons.
    """
    if rule is None or rule == {}:
        return RuleResult(True, [])
    ensure_valid_rule(rule)
    return _eval(rule, ctx)


# ----------------------------
# Plain-English description (for reviewers)
# ----------------------------

def describe_rule(rule: Any) -> str:
    """A short plain-English reading of a rule, e.g. 'respondent is the chair and the item is about themselves'."""
    if rule is None or rule == {}:
        return "always"
    if validate_rule(rule):
        return "invalid rule"
    return _describe(rule)


def _describe(rule: Dict[str, Any]) -> str:
    (name, arg), = rule.items()
    if name in ("all", "any"):
        if len(arg) == 1:
            return _describe(arg[0])
        joiner = " and " if name == "all" else " or "
        # Bracket nested groups only; a single condition reads fine on its own
        return joiner.join(
            f"({_describe(r)})" if next(iter(r)) in ("all", "any") and len(r[next(iter(r))]) > 1 else _describe(r)
            for r in arg
        )
    if name == "not":
        return f"not ({_describe(arg)})"
    roles = lambda xs: _or_list([ROLE_PHRASES.get(x, x) for x in xs])  # noqa: E731
    types = lambda xs: _or_list([SUBJECT_TYPE_NAMES.get(x, x) for x in xs])  # noqa: E731
    phrases = {
        "respondent.role": lambda a: f"respondent is {roles(a)}",
        "respondent.is_subject": lambda a: "the item is about the respondent",
        "respondent.is_not_subject": lambda a: "the item is about someone other than the respondent",
        "respondent.is_member_of_subject_committee": lambda a: "respondent sits on the committee",
        "respondent.chairs_subject_committee": lambda a: "respondent chairs the committee",
        "subject.type": lambda a: f"the item is about {types(a)}",
        "subject.committee_type": lambda a: f"the committee is {_or_list(a)}",
        "subject.committee_name_contains": lambda a: f"the committee name contains {_or_list([repr(w) for w in a])}",
        "org.sector": lambda a: f"the company is in {_or_list(a)}",
        "org.has_code": lambda a: f"the evaluation uses {_code_name(a)}",
        "evaluation.scope_includes": lambda a: f"the scope includes {SUBJECT_TYPE_NAMES.get(a, a)}",
        "evaluation.option": lambda a: f"{a['key'].replace('_', ' ')} is {a['value']!r}",
        "fact.known": lambda a: f"{fact_label(a)} is known",
        "fact.unknown": lambda a: f"{fact_label(a)} is not known",
        "fact.at_least": lambda a: f"{fact_label(a['key'])} is at least {a['value']}",
        "fact.at_most": lambda a: f"{fact_label(a['key'])} is at most {a['value']}",
    }
    return phrases[name](arg)


def conditions_for_ui() -> List[Dict[str, str]]:
    return [{"name": n, "argument": spec[0]} for n, spec in CONDITIONS.items()]
