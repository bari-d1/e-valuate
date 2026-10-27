"""
app.services.question_selection
-------------------------------
Preview which question bank items each participant of an evaluation would
get, about which subject, and why. Preview only: nothing is created.

Two layers:
- build_selection_context(db, ev): reads the evaluation, organisation,
  participants' confirmed profiles and committees into plain dicts.
- select_for_respondent(items, base, respondent): pure. For each item, works
  out the subject instances it binds to, evaluates the respondent and
  activation rules, fills placeholders and checks known_from. Each instance
  ends up included, skipped (already known), blocked (missing data) or not
  included, always with reasons.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BoardMember,
    CommitteeMembership,
    Evaluation,
    EvaluationGovernanceCode,
    EvaluationScopeSubjectType,
    Organisation,
    OrganisationFact,
    OrganisationGovernanceCode,
    OrgCommittee,
    Participant,
    QuestionBankItem,
)
from app.domain.board_member_profile import (
    GENERATION_ONLY_KEYS,
    governance_role_from_participant_role,
    tenure_years,
)
from app.domain.governance import normalize_sector
from app.domain.question_bank import estimate_seconds, fill_placeholders
from app.domain.question_rules import evaluate, fact_label, format_fact_value, lookup_fact
from app.domain.taxonomy import SUBJECT_TYPE_CODES
from app.services.board_members import confirmed_facts, member_label

# Previews longer than this are flagged for the consultant. The historical
# methodology gives most directors 60-100 minutes, so this marks the outliers.
LONG_PREVIEW_MINUTES = 90

ROLE_TO_SUBJECT_TYPE = {"chair": "CHAIR", "md_ceo": "MD_CEO", "ed": "ED", "ned": "NED", "ined": "INED",
                        "company_secretary": "COMPANY_SECRETARY"}
ROLE_LABELS = {"chair": "Chair", "md_ceo": "MD/CEO", "ed": "Executive director", "ned": "Non-executive director",
               "ined": "Independent NED", "company_secretary": "Company secretary"}


# ----------------------------
# Which version of each item applies
# ----------------------------

def eligible_items(items: List[Any], include_drafts: bool = False) -> List[Any]:
    """
    Per code: the highest version if it's approved (or a draft, when drafts are
    included); otherwise the highest approved version below it. A code whose
    highest version is retired is left out.
    """
    by_code: Dict[str, List[Any]] = {}
    for i in items:
        by_code.setdefault(_get(i, "code"), []).append(i)
    out = []
    for versions in by_code.values():
        versions.sort(key=lambda i: _get(i, "version"), reverse=True)
        if _get(versions[0], "status") == "retired":
            continue
        allowed = ("approved", "draft") if include_drafts else ("approved",)
        pick = next((v for v in versions if _get(v, "status") in allowed), None)
        if pick is not None:
            out.append(pick)
    out.sort(key=lambda i: (_get(i, "sort_order") or 0, _get(i, "code")))
    return out


def _get(item: Any, key: str) -> Any:
    return item[key] if isinstance(item, dict) else getattr(item, key)


def item_spec(item: QuestionBankItem) -> Dict[str, Any]:
    """The fields selection needs, as a plain dict."""
    return {
        "code": item.code, "version": item.version, "status": item.status, "text": item.text,
        "answer_type": item.answer_type, "options": item.options, "subject_types": item.subject_type_codes,
        "subject_binding": item.subject_binding, "respondent_rule": item.respondent_rule,
        "activation_rule": item.activation_rule, "known_from": item.known_from,
        "known_from_behaviour": item.known_from_behaviour, "placeholders": item.placeholders or [],
        "theme_code": item.theme_code, "evidence_source_code": item.evidence_source_code,
        "sort_order": item.sort_order,
    }


# ----------------------------
# Context from the database
# ----------------------------

def _review_year(ev: Evaluation) -> int:
    return ev.review_period_end.year if ev.review_period_end else ev.year


def build_selection_context(db: Session, ev: Evaluation) -> Dict[str, Any]:
    org_facts: Dict[str, Any] = {}
    codes: List[str] = []
    committees: List[Dict[str, Any]] = []
    sector = normalize_sector(ev.sector)[0]

    if ev.organisation_id:
        org = db.get(Organisation, ev.organisation_id)
        sector = org.sector_key or sector
        org_facts = {f.key: f.value for f in db.execute(
            select(OrganisationFact).where(OrganisationFact.organisation_id == org.id, OrganisationFact.status == "confirmed")
        ).scalars().all()}
        for c in db.execute(
            select(OrgCommittee).where(OrgCommittee.organisation_id == org.id, OrgCommittee.status == "confirmed")
            .order_by(OrgCommittee.name)
        ).scalars().all():
            members = db.execute(select(CommitteeMembership).where(
                CommitteeMembership.committee_id == c.id, CommitteeMembership.status == "confirmed")).scalars().all()
            committees.append({
                "kind": "committee", "type": "COMMITTEE", "committee_id": str(c.id), "committee_type": c.committee_type,
                "committee_name": c.name, "label": c.name,
                "facts": {"committee_member_count": len(members) or None},
            })
        codes = [r.code for r in db.execute(
            select(OrganisationGovernanceCode).where(OrganisationGovernanceCode.organisation_id == org.id)
        ).scalars().all()]
    ev_codes = [r.code for r in db.execute(
        select(EvaluationGovernanceCode).where(EvaluationGovernanceCode.evaluation_id == ev.id)
    ).scalars().all()]
    scope = [r.subject_type_code for r in db.execute(
        select(EvaluationScopeSubjectType).where(EvaluationScopeSubjectType.evaluation_id == ev.id)
    ).scalars().all()] or list(SUBJECT_TYPE_CODES)

    confirmed_committee_ids = {c["committee_id"] for c in committees}
    people: List[Dict[str, Any]] = []
    for p in db.execute(
        select(Participant).where(Participant.evaluation_id == ev.id).order_by(Participant.created_at)
    ).scalars().all():
        m = db.get(BoardMember, p.board_member_id) if p.board_member_id else None
        facts: Dict[str, Any] = {}
        member_committees: List[Dict[str, Any]] = []
        role = None
        if m is not None:
            facts = {k: f.value for k, f in confirmed_facts(db, m).items() if k not in GENERATION_ONLY_KEYS}
            role = facts.get("governance_role")
            rows = db.execute(
                select(CommitteeMembership, OrgCommittee)
                .join(OrgCommittee, OrgCommittee.id == CommitteeMembership.committee_id)
                .where(CommitteeMembership.board_member_id == m.id, CommitteeMembership.status == "confirmed")
            ).all()
            member_committees = [
                {"committee_id": str(c.id), "name": c.name, "type": c.committee_type, "role": ms.membership_role}
                for ms, c in rows if str(c.id) in confirmed_committee_ids
            ]
        role = role or governance_role_from_participant_role(p.role)
        # Tenure at the end of the review period, not today: the questionnaire is about that period.
        facts["tenure_years"] = tenure_years(facts.get("board_appointment_date"), ev.review_period_end)
        facts["committee_types"] = sorted({c["type"] for c in member_committees}) or None
        people.append({
            "participant_id": str(p.id),
            "board_member_id": str(m.id) if m else None,
            "label": member_label(m) if m else (p.full_name or p.email),
            "role": role,
            "committees": member_committees,
            "facts": facts,
        })

    return {
        "org": {"sector": sector, "codes": ev_codes or codes, "facts": org_facts},
        "evaluation": {"id": ev.id, "scope": scope, "review_year": _review_year(ev)},
        "people": people,
        "committees": committees,
    }


# ----------------------------
# Selection (pure)
# ----------------------------

def _person_subject(person: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    t = ROLE_TO_SUBJECT_TYPE.get(person.get("role") or "")
    if not t:
        return None
    return {"kind": "person", "type": t, "participant_id": person["participant_id"], "label": person["label"],
            "facts": person.get("facts") or {}}


def subject_instances(item: Dict[str, Any], base: Dict[str, Any], respondent: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The subjects an item is asked about for this respondent (before rules)."""
    scope = set(base["evaluation"]["scope"])
    types = [t for t in item["subject_types"] if t in scope]
    binding = item["subject_binding"]
    if binding == "none":
        for t in types:
            if t == "BOARD":
                return [{"kind": "board", "type": "BOARD", "label": "The board", "facts": {}}]
            if t == "COMPANY_SECRETARY":
                return [{"kind": "function", "type": "COMPANY_SECRETARY", "label": "The company secretariat", "facts": {}}]
        return []
    if binding == "self":
        me = _person_subject(respondent)
        return [me] if me and me["type"] in types else []
    if binding == "respondent_committees":
        if "COMMITTEE" not in types:
            return []
        mine = {c["committee_id"] for c in respondent.get("committees") or []}
        return [c for c in base["committees"] if c["committee_id"] in mine]
    out: List[Dict[str, Any]] = []
    if "BOARD" in types:
        out.append({"kind": "board", "type": "BOARD", "label": "The board", "facts": {}})
    for person in base["people"]:
        s = _person_subject(person)
        if s and s["type"] in types:
            out.append(s)
    if "COMMITTEE" in types:
        out.extend(base["committees"])
    return out


def _subject_ref(s: Dict[str, Any]) -> Dict[str, Any]:
    key = s.get("participant_id") or s.get("committee_id") or s["type"]
    return {"key": f"{s['kind']}:{key}", "kind": s["kind"], "type": s["type"], "label": s["label"],
            "participant_id": s.get("participant_id"), "committee_id": s.get("committee_id")}


def select_for_respondent(items: List[Dict[str, Any]], base: Dict[str, Any], respondent: Dict[str, Any]) -> Dict[str, Any]:
    included: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    not_included: List[Dict[str, Any]] = []
    resp_ctx = {k: respondent.get(k) for k in ("participant_id", "label", "role", "committees", "facts")}

    for item in items:
        for subject in subject_instances(item, base, respondent):
            ctx = {"respondent": resp_ctx, "subject": subject, "org": base["org"], "evaluation": base["evaluation"]}
            results = [evaluate(item["respondent_rule"], ctx), evaluate(item["activation_rule"], ctx)]
            entry = {"code": item["code"], "version": item["version"], "status": item["status"],
                     "subject": _subject_ref(subject)}
            if any(r.value is False for r in results):
                entry["reasons"] = [x for r in results if r.value is False for x in r.reasons]
                not_included.append(entry)
                continue
            if any(r.value is None for r in results):
                entry.update(text=item["text"], reasons=[x for r in results if r.value is None for x in r.reasons],
                             missing=[x for r in results for x in r.missing])
                blocked.append(entry)
                continue
            reasons = [x for r in results for x in r.reasons]

            values: Dict[str, str] = {}
            missing = []
            for key in item["placeholders"]:
                known, v = lookup_fact(ctx, key)
                if known:
                    values[key] = format_fact_value(v)
                else:
                    missing.append(fact_label(key))
            if missing:
                entry.update(text=item["text"], reasons=[f"the wording needs {', '.join(missing)}"], missing=missing)
                blocked.append(entry)
                continue
            text = fill_placeholders(item["text"], values)
            options = [fill_placeholders(o, values) for o in item["options"]] if item.get("options") else None

            confirm_value = None
            if item["known_from"]:
                known, v = lookup_fact(ctx, item["known_from"])
                if known:
                    stored = {"known_from": item["known_from"], "known_from_label": fact_label(item["known_from"]),
                              "value": v, "value_text": format_fact_value(v)}
                    if item["known_from_behaviour"] == "skip":
                        skipped.append({**entry, "text": text, **stored,
                                        "why": f"Skipped: {stored['known_from_label']} is already confirmed ({stored['value_text']})"})
                        continue
                    confirm_value = stored

            seconds = estimate_seconds(item["answer_type"], confirm=confirm_value is not None)
            why = "Included: " + (" and ".join(reasons) if reasons else "no conditions")
            if confirm_value:
                why += f"; asks them to confirm the stored {confirm_value['known_from_label'].lower()}"
            included.append({**entry, "text": text, "options": options, "answer_type": item["answer_type"],
                             "theme_code": item["theme_code"], "evidence_source_code": item["evidence_source_code"],
                             "reasons": reasons, "why": why, "confirm": confirm_value, "seconds": seconds})

    seconds = sum(i["seconds"] for i in included)
    minutes = round(seconds / 60)
    return {
        "participant_id": respondent["participant_id"],
        "board_member_id": respondent.get("board_member_id"),
        "label": respondent["label"],
        "role": respondent.get("role"),
        "role_label": ROLE_LABELS.get(respondent.get("role") or "", "Role not confirmed"),
        "counts": {
            "included": len(included),
            "to_confirm": sum(1 for i in included if i["confirm"]),
            "skipped": len(skipped),
            "blocked": len(blocked),
            "not_included": len(not_included),
            "subjects": len({i["subject"]["key"] for i in included}),
        },
        "estimated_minutes": minutes,
        "long": minutes > LONG_PREVIEW_MINUTES,
        "included": included,
        "skipped": skipped,
        "blocked": blocked,
        "not_included": not_included,
    }


# ----------------------------
# Preview
# ----------------------------

def preview(db: Session, ev: Evaluation, *, participant_id: Optional[str] = None,
            include_drafts: bool = False) -> Dict[str, Any]:
    base = build_selection_context(db, ev)
    all_items = db.execute(select(QuestionBankItem)).scalars().all()
    items = [item_spec(i) for i in eligible_items(all_items, include_drafts)]
    people = base["people"]
    if participant_id:
        people = [p for p in people if p["participant_id"] == participant_id]
    warnings = []
    if not items:
        warnings.append("No approved question bank items yet." + ("" if include_drafts else " Include drafts to preview the draft bank."))
    if not base["org"]["codes"]:
        warnings.append("No governance codes are set for this evaluation, so code-specific items are blocked.")
    if not base["org"]["sector"]:
        warnings.append("The company's sector isn't set, so sector-specific items are blocked.")
    no_role = [p["label"] for p in people if not p["role"]]
    if no_role:
        warnings.append(f"No confirmed governance role for: {', '.join(no_role)}.")
    return {
        "evaluation_id": ev.id,
        "include_drafts": include_drafts,
        "items_considered": len(items),
        "long_preview_minutes": LONG_PREVIEW_MINUTES,
        "context": {
            "sector": base["org"]["sector"],
            "governance_codes": base["org"]["codes"],
            "scope": base["evaluation"]["scope"],
            "review_year": base["evaluation"]["review_year"],
            "committees": [{"committee_id": c["committee_id"], "name": c["label"], "committee_type": c["committee_type"]}
                           for c in base["committees"]],
        },
        "warnings": warnings,
        "participants": [select_for_respondent(items, base, p) for p in people],
    }

