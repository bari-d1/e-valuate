"""
A VAL-001-style evaluation for tests: an insurer under NCCG 2018 and NAICOM 2021
with three committees and seven participants (placeholder names and emails only):

    P001 chair, P002 MD/CEO, P003 ED, P004 and P005 NEDs, P006 INED, P007 company secretary

Profiles are reviewed and roles confirmed, so every participant is ready.
"""

from __future__ import annotations

from datetime import date

from app.db.models import (
    BoardMember,
    BoardMemberFact,
    CommitteeMembership,
    Evaluation,
    EvaluationGovernanceCode,
    Organisation,
    OrganisationFact,
    OrgCommittee,
    Participant,
)
from app.domain.board_member_profile import PARTICIPANT_ROLE_FOR

ROSTER = [
    ("P001", "chair", "2018-01-15"),
    ("P002", "md_ceo", "2020-06-01"),
    ("P003", "ed", "2021-02-01"),
    ("P004", "ned", "2017-09-01"),
    ("P005", "ned", None),
    ("P006", "ined", "2019-03-01"),
    ("P007", "company_secretary", None),
]
COMMITTEES = [
    ("Audit and Compliance Committee", "audit", {"P006": "chair", "P004": "member", "P005": "member"}),
    ("Enterprise Risk Management and Governance Committee", "governance", {"P004": "chair", "P006": "member", "P002": "member"}),
    ("Finance and Investment Committee", "finance", {"P005": "chair", "P002": "member", "P003": "member", "P004": "member"}),
]


def _confirmed(model, **kw):
    return model(source="client", status="confirmed", origin="manual", **kw)


def build_val001(db, *, sector="insurance", codes=("NCCG_2018", "NAICOM_2021"), eid="VAL-001",
                 board_composition=True, ined_facts=True):
    org = Organisation(name=f"{eid} Test Company", sector_key=sector, country="NG")
    db.add(org)
    db.flush()
    db.add(_confirmed(OrganisationFact, organisation_id=org.id, key="board_size", value=6))
    if board_composition:
        db.add(_confirmed(OrganisationFact, organisation_id=org.id, key="board_composition",
                          value={"executive_directors": 2, "non_executive_directors": 3,
                                 "independent_non_executive_directors": 1, "women": 1, "men": 5}))
    ev = Evaluation(id=eid, tenant_name=org.name, sector=sector, year=2025, regulators={"items": []},
                    organisation_id=org.id, review_period_end=date(2025, 12, 31))
    db.add(ev)
    db.flush()
    for code in codes:
        db.add(EvaluationGovernanceCode(evaluation_id=ev.id, code=code, source="manual"))

    members, participants = {}, {}
    for code, role, appointed in ROSTER:
        m = BoardMember(organisation_id=org.id, full_name=f"Board Member {code[1:]}", email=f"{code}@example.invalid",
                        display_code=code, active=True, profile_status="reviewed", profile_version=2)
        db.add(m)
        db.flush()
        db.add(_confirmed(BoardMemberFact, board_member_id=m.id, key="governance_role", value=role))
        if appointed:
            db.add(_confirmed(BoardMemberFact, board_member_id=m.id, key="board_appointment_date", value=appointed))
        db.add(_confirmed(BoardMemberFact, board_member_id=m.id, key="expertise", value=["Finance"]))
        p = Participant(evaluation_id=ev.id, email=m.email, full_name=m.full_name, role=PARTICIPANT_ROLE_FOR[role],
                        board_member_id=m.id, status="invited")
        db.add(p)
        members[code], participants[code] = m, p
    if ined_facts:
        for key in ("holds_company_shares", "represents_significant_shareholder",
                    "employee_of_company_or_group_last_5y", "close_family_tie_to_director_adviser_or_auditor"):
            db.add(_confirmed(BoardMemberFact, board_member_id=members["P006"].id, key=key, value={"answer": "no"}))
    committees = {}
    for name, ctype, seats in COMMITTEES:
        c = _confirmed(OrgCommittee, organisation_id=org.id, name=name, committee_type=ctype, member_names=[])
        db.add(c)
        db.flush()
        committees[name] = c
        for code, seat in seats.items():
            db.add(CommitteeMembership(committee_id=c.id, board_member_id=members[code].id, membership_role=seat,
                                       source="client", status="confirmed", origin="manual"))
    db.flush()
    return ev, participants, committees
