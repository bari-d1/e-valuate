"""
Question selection preview on a VAL-001-style evaluation: an insurer under
NCCG 2018 and NAICOM 2021 with three committees and seven participants
(placeholder names and emails only):

    P001 chair, P002 MD/CEO, P003 ED, P004 and P005 NEDs, P006 INED, P007 company secretary

The draft bank is loaded and previewed with drafts included.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db.models import AssessmentAssignment, Participant, Question
from app.services.question_bank import load_fixture
from app.services.question_selection import LONG_PREVIEW_MINUTES, eligible_items, preview
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"

@pytest.fixture
def bank(db_session, reference_seeded):
    summary = load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert not summary["errors"]
    return summary


@pytest.fixture
def val001(db_session, bank):
    return build_val001(db_session)


def _by_code(result):
    return {p["label"].split(" · ")[0]: p for p in result["participants"]}


def _codes(entries, prefix=""):
    return [e["code"] for e in entries if e["code"].startswith(prefix)]


@pytest.fixture
def result(db_session, val001):
    ev, _, _ = val001
    return _by_code(preview(db_session, ev, include_drafts=True))


def test_preview_needs_approved_items_unless_drafts_included(db_session, val001) -> None:
    ev, _, _ = val001
    out = preview(db_session, ev)
    assert out["items_considered"] == 0
    assert any("No approved" in w for w in out["warnings"])
    assert preview(db_session, ev, include_drafts=True)["items_considered"] == 288


def test_ined_gets_independence_items_and_known_ones_are_skipped(result) -> None:
    p6 = result["P006"]
    included = {e["code"]: e for e in p6["included"]}
    skipped = {e["code"]: e for e in p6["skipped"]}
    assert set(_codes(p6["skipped"], "INED-IND-")) == {"INED-IND-01", "INED-IND-02", "INED-IND-03", "INED-IND-04", "INED-IND-09"}
    assert set(_codes(p6["included"], "INED-IND-")) == {"INED-IND-05", "INED-IND-06", "INED-IND-07", "INED-IND-08"}
    assert skipped["INED-IND-01"]["value_text"] == "No"
    assert skipped["INED-IND-01"]["why"] == "Skipped: Holds shares in the company is already confirmed (No)"
    assert skipped["INED-IND-09"]["known_from"] == "tenure_years"
    # Counted to the end of the review period (31 Dec 2025), not to today
    assert skipped["INED-IND-09"]["value"] == 6.8  # appointed 1 Mar 2019
    assert included["INED-IND-05"]["why"] == "Included: respondent is an independent NED and the item is about themselves"
    for code in ("P001", "P002", "P003", "P004", "P005", "P007"):
        assert not _codes(result[code]["included"] + result[code]["skipped"], "INED-IND-"), code


def test_committee_items_go_to_members_once_per_committee(result, val001) -> None:
    _, _, committees = val001
    ids = {name: str(c.id) for name, c in committees.items()}

    def subjects(p, code):
        return sorted(e["subject"]["committee_id"] for e in p["included"] if e["code"] == code)

    assert subjects(result["P004"], "COM-CORE-01") == sorted(ids.values())  # sits on all three
    assert subjects(result["P003"], "COM-CORE-01") == [ids["Finance and Investment Committee"]]
    assert subjects(result["P006"], "COM-CORE-01") == sorted([ids["Audit and Compliance Committee"],
                                                              ids["Enterprise Risk Management and Governance Committee"]])
    for code in ("P001", "P007"):
        assert not _codes(result[code]["included"], "COM-"), code
    # Committee-specific items follow the committee type
    assert subjects(result["P004"], "COM-AUDIT-02") == [ids["Audit and Compliance Committee"]]
    assert subjects(result["P004"], "COM-ERMG-02") == [ids["Enterprise Risk Management and Governance Committee"]]
    assert subjects(result["P004"], "COM-FIN-02") == [ids["Finance and Investment Committee"]]
    assert not _codes(result["P004"]["included"], "COM-SAC-"), "no statutory audit committee here"
    # Committee size is known from memberships
    assert {e["subject"]["label"] for e in result["P004"]["skipped"] if e["code"] == "COM-CORE-03"} == set(ids)


def _about(p, code):
    return {e["subject"]["participant_id"] for e in p["included"] if e["code"] == code}


DIRECTORS = ("P001", "P002", "P003", "P004", "P005", "P006")


def test_core_peer_items_go_to_every_other_director(result, val001) -> None:
    _, participants, _ = val001
    pid = {code: str(p.id) for code, p in participants.items()}
    for code in DIRECTORS:
        others = {pid[c] for c in DIRECTORS if c != code}
        p = result[code]
        assert _about(p, "PEER-CORE-01") == others, code  # never themselves, never P007
        assert _about(p, "PEER-COMMENT-01") == others, code
        assert _about(p, "PEER-CORE-05") == {pid[c] for c in ("P001", "P004", "P005", "P006") if c != code}
        assert _about(p, "PEER-CORE-06") == {pid[c] for c in ("P002", "P003") if c != code}
        assert {e["code"] for e in p["included"] if e["code"].startswith("SELF-CORE-")} == (
            {f"SELF-CORE-0{n}" for n in (1, 2, 3, 4)} | {"SELF-CORE-06" if code in ("P002", "P003") else "SELF-CORE-05"})
        assert all(e["subject"]["participant_id"] == pid[code] for e in p["included"] if e["code"].startswith("SELF-CORE-"))
        assert not _codes(p["included"], "PEER-NED-") and not _codes(p["included"], "PEER-EXEC-")
        assert not _codes(p["included"], "CHAIR-PEER-")
    assert not _codes(result["P007"]["included"], "PEER-") and not _codes(result["P007"]["included"], "SELF-CORE-")


def test_deep_sets_go_to_those_best_placed(result, val001) -> None:
    _, participants, _ = val001
    pid = {code: str(p.id) for code, p in participants.items()}
    chair_deep = {code: _codes(result[code]["included"], "DEEP-CHAIR-") for code in result}
    for code in ("P004", "P005", "P006"):
        assert len(chair_deep[code]) == 9, code
    assert sorted(chair_deep["P002"]) == ["DEEP-CHAIR-06", "DEEP-CHAIR-07", "DEEP-CHAIR-08", "DEEP-CHAIR-09"]
    assert chair_deep["P003"] == [] and chair_deep["P001"] == [] and chair_deep["P007"] == []
    md_raters = {code for code in result if _codes(result[code]["included"], "DEEP-MD-")}
    assert md_raters == {"P001", "P004", "P005", "P006"}
    ed_raters = {code for code in result if _codes(result[code]["included"], "DEEP-ED-")}
    assert ed_raters == {"P001", "P002"}
    assert _about(result["P001"], "DEEP-ED-01") == {pid["P003"]}


def test_full_peer_mode_restores_the_original_forms(db_session, val001) -> None:
    ev, participants, _ = val001
    ev.options = {"peer_mode": "full"}
    db_session.flush()
    result = _by_code(preview(db_session, ev, include_drafts=True))
    pid = {code: str(p.id) for code, p in participants.items()}
    nominees = {"P004", "P005", "P006"}
    for code in DIRECTORS:
        assert _about(result[code], "PEER-NED-01") == {pid[c] for c in nominees - {code}}, code
        assert _about(result[code], "PEER-EXEC-01") == {pid[c] for c in {"P002", "P003"} - {code}}, code
        assert not _codes(result[code]["included"], "PEER-CORE-") and not _codes(result[code]["included"], "DEEP-")
        for e in result[code]["included"]:
            if e["code"].startswith(("PEER-", "CHAIR-PEER-")):
                assert e["subject"]["participant_id"] != pid[code]
    for code in ("P002", "P003", "P004", "P005", "P006", "P007"):
        assert _about(result[code], "CHAIR-PEER-01") == {pid["P001"]}
    assert _about(result["P001"], "PEER-EXEC-03") == {pid["P003"]}


def test_chair_self_items_reach_only_the_chair(result) -> None:
    assert len(_codes(result["P001"]["included"], "CHAIR-SELF-")) == 7
    for code in ("P002", "P003", "P004", "P005", "P006", "P007"):
        assert not _codes(result[code]["included"], "CHAIR-SELF-"), code


def test_secretariat_items_reach_only_the_secretary(result) -> None:
    p7 = result["P007"]
    assert len(_codes(p7["included"], "SEC-")) == 70
    assert {e["subject"]["kind"] for e in p7["included"] if e["code"].startswith("SEC-")} == {"function"}
    confirm = {e["code"]: e["confirm"]["value_text"] for e in p7["included"] if e["confirm"]}
    assert confirm["SEC-04"] == "6"  # total board members, asked to confirm the stored board size
    for code in ("P001", "P002", "P003", "P004", "P005", "P006"):
        assert not _codes(result[code]["included"], "SEC-"), code
    assert not _codes(p7["included"], "BOARD-"), "the whole-board form is for directors"


def test_placeholders_are_filled_from_confirmed_facts(result) -> None:
    item = next(e for e in result["P001"]["included"] if e["code"] == "BOARD-EFF-01")
    assert item["text"].startswith("Your board has 1 female member(s).")
    year = next(e for e in result["P002"]["included"] if e["code"] == "EXEC-SELF-04")
    assert year["text"] == "Did you have board-approved KPI targets for 2025?"


def test_counts_and_time(result) -> None:
    for code, p in result.items():
        c = p["counts"]
        assert c["included"] == len(p["included"]) and c["skipped"] == len(p["skipped"]) and c["blocked"] == len(p["blocked"])
        assert p["estimated_minutes"] == round(sum(e["seconds"] for e in p["included"]) / 60)
        assert p["estimated_minutes"] > 0, code
        assert p["blocked"] == [], (code, p["blocked"][:2])
        assert p["long"] is (p["estimated_minutes"] > LONG_PREVIEW_MINUTES)
    assert result["P004"]["long"] is True  # three committees and both deep sets


def test_item_limited_to_insurance_or_naicom_does_not_reach_a_bank(db_session, bank) -> None:
    ev, _, _ = build_val001(db_session, sector="banking", codes=("NCCG_2018", "CBN_BANKS_2023"), eid="VAL-BANK")
    out = _by_code(preview(db_session, ev, include_drafts=True))
    naicom = {"CHAIR-SELF-01", "CHAIR-SELF-02", "CHAIR-SELF-05", "ROLE-SELF-01", "BOARD-EFF-03", "EXEC-SELF-01"}
    for code, p in out.items():
        assert not naicom & set(_codes(p["included"])), code
    reasons = {e["code"]: e["reasons"] for e in out["P001"]["not_included"]}
    assert reasons["CHAIR-SELF-01"] == ["the evaluation isn't assessed against NAICOM 2021"]
    # Items that aren't sector-specific still apply
    assert "BOARD-STR-03" in _codes(out["P001"]["included"])


def test_missing_data_blocks_instead_of_excluding(db_session, bank) -> None:
    ev, participants, _ = build_val001(db_session, board_composition=False, eid="VAL-GAPS")
    db_session.add(Participant(evaluation_id=ev.id, email="P008@example.invalid", full_name="Unlinked Person", status="invited"))
    db_session.flush()
    out = _by_code(preview(db_session, ev, include_drafts=True))
    blocked = {e["code"]: e for e in out["P001"]["blocked"]}
    assert blocked["BOARD-EFF-01"]["missing"] == ["Board composition: Women"]
    unlinked = out["Unlinked Person"]
    assert unlinked["role_label"] == "Role not confirmed"
    assert unlinked["included"] == [] and unlinked["blocked"]
    assert all("respondent's governance role" in e["missing"] for e in unlinked["blocked"])


def test_preview_creates_nothing(db_session, val001) -> None:
    ev, _, _ = val001
    before = [db_session.scalar(select(func.count()).select_from(m)) for m in (Question, AssessmentAssignment)]
    preview(db_session, ev, include_drafts=True)
    after = [db_session.scalar(select(func.count()).select_from(m)) for m in (Question, AssessmentAssignment)]
    assert before == after


def test_preview_api(api_client, val001) -> None:
    ev, participants, _ = val001
    r = api_client.get(f"/api/v1/evaluations/{ev.id}/question-preview", params={"include_drafts": True})
    assert r.status_code == 200
    assert len(r.json()["participants"]) == 7
    r = api_client.get(f"/api/v1/evaluations/{ev.id}/question-preview",
                       params={"include_drafts": True, "participant_id": str(participants["P006"].id)})
    assert [p["label"] for p in r.json()["participants"]] == ["P006 · Board Member 006"]
    assert api_client.get("/api/v1/evaluations/NOPE/question-preview").status_code == 404
    assert api_client.get(f"/api/v1/evaluations/{ev.id}/question-preview",
                          params={"participant_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404


# ----------------------------
# Version choice (pure)
# ----------------------------

def _v(code, version, status):
    return {"code": code, "version": version, "status": status, "sort_order": 0}


def test_eligible_items_pick_the_right_version() -> None:
    items = [_v("A-01", 1, "approved"), _v("A-01", 2, "draft"),
             _v("B-01", 1, "approved"), _v("B-01", 2, "retired"),
             _v("C-01", 1, "draft")]
    assert [(i["code"], i["version"]) for i in eligible_items(items)] == [("A-01", 1)]
    assert [(i["code"], i["version"]) for i in eligible_items(items, include_drafts=True)] == [("A-01", 2), ("C-01", 1)]
