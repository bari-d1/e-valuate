"""
app.services.committee_matching
-------------------------------
Propose committee memberships by matching the names written on a company's
committees (chair_name, member_names) against its board members.

Only EXACT matches after normalising are proposed. Normalising removes case,
spacing, punctuation and honorifics (Mr, Mrs, Ms, Miss, Dr, Prof, Chief, Alhaji,
Alhaja, Engr, Sir). Anything else is listed for the consultant, as a near-miss
(with the closest board members) or as unmatched. Nothing is guessed.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BoardMember, CommitteeMembership, Organisation, OrgCommittee
from app.services.board_members import member_label

HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "chief", "alhaji", "alhaja", "engr", "sir"}
NEAR_MISS_RATIO = 0.8
MAX_CANDIDATES = 3


def normalise_name(name: Optional[str]) -> str:
    """'Chief (Mrs.) Ada  OBI' -> 'ada obi'."""
    s = (name or "").casefold()
    s = re.sub(r"[^\w\s]", " ", s)          # punctuation, incl. brackets and full stops
    s = s.replace("_", " ")
    tokens = [t for t in s.split() if t]
    while tokens and tokens[0] in HONORIFICS:  # honorifics are leading titles ("Prof Dr ...")
        tokens.pop(0)
    tokens = [t for t in tokens if t not in HONORIFICS]
    return " ".join(tokens)


def _near(a: str, b: str) -> Optional[str]:
    """Why two normalised names look alike without matching exactly, or None."""
    if not a or not b:
        return None
    ta, tb = a.split(), b.split()
    if set(ta) == set(tb):
        return "same names in a different order"
    if set(ta) < set(tb) or set(tb) < set(ta):
        return "one name has extra parts"
    if ta[-1] == tb[-1] and ta[0][0] == tb[0][0]:
        return "same surname and first initial"
    if difflib.SequenceMatcher(None, a, b).ratio() >= NEAR_MISS_RATIO:
        return "similar spelling"
    return None


def _candidate(m: BoardMember, reason: str) -> Dict[str, Any]:
    return {"board_member": member_label(m), "board_member_id": str(m.id), "reason": reason}


def match_committee_members(db: Session, org: Organisation) -> Dict[str, Any]:
    """
    Propose memberships for the company's confirmed committees. Existing links
    (confirmed, proposed or rejected) are not changed, except that a proposed
    link's member/chair role is refreshed. Inactive members are never proposed;
    an exact match with one is listed as a near-miss saying so. Flushes but does
    not commit.

    Returns lists: proposed, already_linked (confirmed or proposed links),
    previously_rejected, near_misses (with candidates), unmatched, skipped_committees.
    """
    members = db.execute(select(BoardMember).where(BoardMember.organisation_id == org.id)).scalars().all()
    by_norm: Dict[str, List[BoardMember]] = {}
    inactive_by_norm: Dict[str, List[BoardMember]] = {}
    for m in members:
        (by_norm if m.active else inactive_by_norm).setdefault(normalise_name(m.full_name), []).append(m)

    committees = db.execute(
        select(OrgCommittee).where(OrgCommittee.organisation_id == org.id).order_by(OrgCommittee.name)
    ).scalars().all()

    result: Dict[str, Any] = {"proposed": [], "already_linked": [], "previously_rejected": [], "near_misses": [],
                              "unmatched": [], "skipped_committees": []}
    for c in committees:
        if c.status != "confirmed":
            result["skipped_committees"].append({"committee": c.name, "reason": f"committee is {c.status}"})
            continue
        links = {ms.board_member_id: ms for ms in db.execute(
            select(CommitteeMembership).where(CommitteeMembership.committee_id == c.id)).scalars()}
        names: Dict[str, str] = {}  # written name -> role (chair wins if listed twice)
        for n in c.member_names or []:
            if (n or "").strip():
                names.setdefault(n.strip(), "member")
        if (c.chair_name or "").strip():
            names[c.chair_name.strip()] = "chair"
        chair_norm = normalise_name(c.chair_name)
        seen_members = set()

        def linked(entry, m, ms):
            key = "previously_rejected" if ms.status == "rejected" else "already_linked"
            result[key].append({**entry, "board_member_id": str(m.id), "board_member": member_label(m),
                                "status": ms.status})

        for written, role in names.items():
            norm = normalise_name(written)
            if role == "member" and norm and norm == chair_norm:
                continue  # the chair also appears in the member list: one link, as chair
            hits = by_norm.get(norm, [])
            entry = {"committee_id": str(c.id), "committee": c.name, "name": written, "membership_role": role}
            if len(hits) == 1 and hits[0].id not in seen_members:
                m = hits[0]
                seen_members.add(m.id)
                ms = links.get(m.id)
                if ms is None:
                    ms = CommitteeMembership(
                        committee_id=c.id, board_member_id=m.id, membership_role=role, source=c.source,
                        status="proposed", origin="name_match", matched_name=written,
                    )
                    db.add(ms)
                    links[m.id] = ms
                    result["proposed"].append({**entry, "board_member_id": str(m.id), "board_member": member_label(m)})
                else:
                    if ms.status == "proposed" and ms.membership_role != role:
                        ms.membership_role = role
                    linked(entry, m, ms)
                continue
            if len(hits) > 1:
                result["near_misses"].append({**entry, "reason": "several board members have this name",
                                              "candidates": [_candidate(m, "same name") for m in hits]})
                continue
            inactive = inactive_by_norm.get(norm, [])
            if inactive:
                result["near_misses"].append({**entry, "reason": "matches an inactive board member",
                                              "candidates": [_candidate(m, "inactive") for m in inactive]})
                continue
            scored = []
            for key, ms_ in by_norm.items():
                why = _near(norm, key)
                if why:
                    score = difflib.SequenceMatcher(None, norm, key).ratio()
                    scored += [(score, m, why) for m in ms_]
            scored.sort(key=lambda x: -x[0])
            # A near-miss someone has already linked by hand to this committee is settled
            settled = next(((m, links[m.id]) for _, m, _ in scored if m.id in links), None)
            if settled:
                linked(entry, *settled)
                continue
            candidates = [_candidate(m, why) for _, m, why in scored[:MAX_CANDIDATES]]  # the closest few
            if candidates:
                result["near_misses"].append({**entry, "candidates": candidates})
            else:
                result["unmatched"].append(entry)
    db.flush()
    return result
