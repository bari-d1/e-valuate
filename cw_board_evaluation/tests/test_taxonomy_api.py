"""
API tests: GET /taxonomy, evaluation subjects, and tags on question endpoints.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import pytest

from app.db.models import Evaluation, Participant, Theme

pytestmark = pytest.mark.integration

EVAL_ID = "eval-taxonomy-api"
LEGACY_CREATE_KEYS = {"created", "question_id", "message"}
LEGACY_PATCH_KEYS = {"updated", "question_id", "template_code", "version", "dimension", "text", "answer_type", "weight", "active"}
TAG_KEYS = {"theme_code", "evidence_source_code", "subject_type_codes"}


@pytest.fixture
def evaluation(db_session, taxonomy_seeded):
    db_session.add(Evaluation(
        id=EVAL_ID, tenant_name="Taxonomy API", sector="insurance", year=2025,
        instrument_template_code="DEFAULT", instrument_version=1, regulators={"items": []},
    ))
    db_session.flush()
    return EVAL_ID


def _create(api_client, text: str, **tags):
    body = {"template_code": "TAXO", "version": 1, "dimension": "Strategy Oversight", "text": text, **tags}
    return api_client.post(f"/api/v1/evaluations/{EVAL_ID}/questions", json=body)


def _list(api_client):
    res = api_client.get(f"/api/v1/evaluations/{EVAL_ID}/questions", params={"template_code": "TAXO", "version": 1})
    assert res.status_code == 200, res.text
    return {q["text"]: q for q in res.json()["items"]}


# ----------------------------
# Taxonomy
# ----------------------------

def test_taxonomy_lists_active_sorted(api_client, db_session, taxonomy_seeded) -> None:
    db_session.get(Theme, "INDEPENDENCE").active = 0
    db_session.flush()

    res = api_client.get("/api/v1/taxonomy")
    assert res.status_code == 200, res.text
    data = res.json()

    assert [s["code"] for s in data["subject_types"]] == [
        "BOARD", "CHAIR", "MD_CEO", "ED", "NED", "INED", "COMMITTEE", "COMPANY_SECRETARY",
    ]
    assert {s["code"]: s["cardinality"] for s in data["subject_types"]}["COMMITTEE"] == "per_committee"
    theme_codes = [t["code"] for t in data["themes"]]
    assert len(theme_codes) == 11 and "INDEPENDENCE" not in theme_codes
    assert theme_codes[0] == "BOARD_EFFECTIVENESS" and theme_codes[-1] == "GENERAL"
    assert [e["code"] for e in data["evidence_sources"]] == ["PERCEPTION", "ROLE_SELF", "ORG_FACT"]


# ----------------------------
# Subjects
# ----------------------------

def test_subjects_sync_and_list(api_client, db_session, evaluation) -> None:
    db_session.add(Participant(evaluation_id=EVAL_ID, email="a@example.com", full_name="A", role="INED", status="invited"))
    db_session.add(Participant(evaluation_id=EVAL_ID, email="b@example.com", full_name="B", role="Director", status="invited"))
    db_session.flush()

    res = api_client.post(f"/api/v1/evaluations/{EVAL_ID}/subjects/sync")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counts"] == {"created": 2, "existing": 0, "skipped": 1}
    assert body["skipped"][0]["role"] == "Director"

    again = api_client.post(f"/api/v1/evaluations/{EVAL_ID}/subjects/sync").json()
    assert again["counts"] == {"created": 0, "existing": 2, "skipped": 1}

    listed = api_client.get(f"/api/v1/evaluations/{EVAL_ID}/subjects").json()
    assert [s["subject_type_code"] for s in listed["items"]] == ["BOARD", "INED"]


def test_subjects_unknown_evaluation_404(api_client, taxonomy_seeded) -> None:
    assert api_client.get("/api/v1/evaluations/nope/subjects").status_code == 404
    assert api_client.post("/api/v1/evaluations/nope/subjects/sync").status_code == 404


# ----------------------------
# Question tags
# ----------------------------

def test_create_without_tags_unchanged(api_client, evaluation) -> None:
    res = _create(api_client, "No tags question")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["created"] is True and body["message"] == "Question created."
    assert LEGACY_CREATE_KEYS <= set(body)
    assert {k: body[k] for k in TAG_KEYS} == {"theme_code": None, "evidence_source_code": None, "subject_type_codes": []}

    q = _list(api_client)["No tags question"]
    assert q["dimension"] == "Strategy Oversight"
    assert q["theme_code"] is None and q["subject_type_codes"] == []

    # idempotent re-create still reports "Already exists."
    again = _create(api_client, "No tags question").json()
    assert again["created"] is False and again["message"] == "Already exists."


def test_create_with_valid_tags(api_client, evaluation) -> None:
    res = _create(
        api_client, "Tagged question",
        theme_code="strategy", evidence_source_code="PERCEPTION", subject_type_codes=["COMMITTEE", "BOARD", "BOARD"],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["theme_code"] == "STRATEGY"  # codes are normalized to upper case
    assert body["evidence_source_code"] == "PERCEPTION"
    assert body["subject_type_codes"] == ["BOARD", "COMMITTEE"]

    q = _list(api_client)["Tagged question"]
    assert (q["theme_code"], q["evidence_source_code"], q["subject_type_codes"]) == ("STRATEGY", "PERCEPTION", ["BOARD", "COMMITTEE"])
    assert q["dimension"] == "Strategy Oversight"  # dimension untouched


@pytest.mark.parametrize(
    "tags,field",
    [
        ({"theme_code": "NOT_A_THEME"}, "theme_code"),
        ({"evidence_source_code": "GUESSWORK"}, "evidence_source_code"),
        ({"subject_type_codes": ["BOARD", "SHAREHOLDER"]}, "subject_type_codes"),
    ],
)
def test_create_with_invalid_codes_400(api_client, evaluation, tags, field) -> None:
    res = _create(api_client, f"Invalid {field}", **tags)
    assert res.status_code == 400, res.text
    assert field in res.json()["detail"]
    assert f"Invalid {field}" not in _list(api_client)


def test_create_with_inactive_theme_400(api_client, db_session, evaluation) -> None:
    db_session.get(Theme, "INDEPENDENCE").active = 0
    db_session.flush()
    assert _create(api_client, "Inactive theme", theme_code="INDEPENDENCE").status_code == 400


def test_patch_tags(api_client, evaluation) -> None:
    qid = _create(api_client, "Patch me").json()["question_id"]

    res = api_client.patch(f"/api/v1/questions/{qid}", json={"theme_code": "RISK_MONITORING", "subject_type_codes": ["INED"]})
    assert res.status_code == 200, res.text
    assert (res.json()["theme_code"], res.json()["subject_type_codes"]) == ("RISK_MONITORING", ["INED"])

    # Omitted tags are left alone; existing fields still work
    res = api_client.patch(f"/api/v1/questions/{qid}", json={"weight": 3})
    body = res.json()
    assert LEGACY_PATCH_KEYS <= set(body)
    assert (body["weight"], body["theme_code"], body["subject_type_codes"]) == (3, "RISK_MONITORING", ["INED"])

    # Invalid code: 400 and nothing changes
    res = api_client.patch(f"/api/v1/questions/{qid}", json={"theme_code": "NOPE", "weight": 5})
    assert res.status_code == 400
    q = _list(api_client)["Patch me"]
    assert (q["theme_code"], q["weight"]) == ("RISK_MONITORING", 3)

    # null / [] clear
    res = api_client.patch(f"/api/v1/questions/{qid}", json={"theme_code": None, "subject_type_codes": []})
    assert (res.json()["theme_code"], res.json()["subject_type_codes"]) == (None, [])


def test_patch_without_tags_unchanged(api_client, evaluation) -> None:
    qid = _create(api_client, "Legacy patch").json()["question_id"]
    res = api_client.patch(f"/api/v1/questions/{qid}", json={"text": "Legacy patch edited", "active": False})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] is True and body["text"] == "Legacy patch edited" and body["active"] is False
    assert body["theme_code"] is None and body["subject_type_codes"] == []


def test_bulk_create_with_tags(api_client, evaluation) -> None:
    res = api_client.post(f"/api/v1/evaluations/{EVAL_ID}/questions/bulk", json={
        "template_code": "TAXO", "version": 1,
        "items": [
            {"dimension": "Open Comments", "text": "Bulk tagged", "answer_type": "comment",
             "theme_code": "GENERAL", "evidence_source_code": "ROLE_SELF", "subject_type_codes": ["ED"]},
            {"dimension": "Open Comments", "text": "Bulk untagged", "answer_type": "comment"},
        ],
    })
    assert res.status_code == 200, res.text
    assert res.json()["created"] == 2
    listed = _list(api_client)
    assert (listed["Bulk tagged"]["theme_code"], listed["Bulk tagged"]["subject_type_codes"]) == ("GENERAL", ["ED"])
    assert listed["Bulk untagged"]["theme_code"] is None


def test_bulk_create_with_invalid_code_400_writes_nothing(api_client, evaluation) -> None:
    res = api_client.post(f"/api/v1/evaluations/{EVAL_ID}/questions/bulk", json={
        "template_code": "TAXO", "version": 1,
        "items": [
            {"dimension": "Open Comments", "text": "Bulk ok", "answer_type": "comment"},
            {"dimension": "Open Comments", "text": "Bulk bad", "answer_type": "comment", "theme_code": "NOPE"},
        ],
    })
    assert res.status_code == 400
    assert "items[1]" in res.json()["detail"]
    assert not ({"Bulk ok", "Bulk bad"} & set(_list(api_client)))
