"""Unit tests for assignment digest email helpers (no SMTP)."""

from app.services.email_service import (
    _dedupe_display_labels,
    _digest_email_subject,
)


def test_dedupe_display_labels_suffixes_duplicates() -> None:
    rows = [
        {"label": "peer (COMM)", "url": "http://a/1"},
        {"label": "peer (COMM)", "url": "http://a/2"},
        {"label": "self", "url": "http://a/3"},
    ]
    out = _dedupe_display_labels(rows)
    assert [r["display_label"] for r in out] == [
        "peer (COMM)",
        "peer (COMM) (2)",
        "self",
    ]


def test_digest_email_subject_single_and_multi() -> None:
    assert _digest_email_subject("eval-001", 1, None) == "Your questionnaire link — eval-001"
    assert _digest_email_subject("eval-001", 3, None) == "Your questionnaire links (3 tasks) — eval-001"
    assert _digest_email_subject("eval-001", 2, "ACME") == (
        "ACME · Your questionnaire links (2 tasks) — eval-001"
    )
