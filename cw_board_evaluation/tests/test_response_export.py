"""Smoke tests for long-format CSV export (no DB)."""

from app.services.response_export import responses_to_csv_bytes


def test_responses_to_csv_bytes_includes_utf8_bom_header():
    row = {
        "response_id": "rid",
        "evaluation_id": "eval-001",
        "assignment_id": None,
        "assignment_type": None,
        "committee_name": None,
        "assignment_status": None,
        "respondent_participant_id": "pid",
        "respondent_email": "x@y.com",
        "respondent_full_name": None,
        "respondent_role": None,
        "subject_participant_id": None,
        "subject_email": None,
        "subject_full_name": None,
        "subject_role": None,
        "question_id": "qid",
        "question_template_code": "DEFAULT",
        "question_version": 1,
        "dimension": "Governance",
        "question_text": "Test?",
        "answer_type": "rating",
        "score": 4,
        "comment": None,
        "response_created_at": "2026-05-01T12:00:00+00:00",
    }
    raw = responses_to_csv_bytes([row])
    assert raw.startswith(b"\xef\xbb\xbf")
    txt = raw.decode("utf-8-sig")
    assert "evaluation_id,assignment_id" in txt.split("\n")[0]
    assert "eval-001" in txt

