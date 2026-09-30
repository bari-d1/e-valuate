"""
Validation and normalization for COMMITTEE_EVAL evaluation_tracks.config.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.db.models import AssessmentTrackTemplate


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _email_norm(s: Optional[str]) -> str:
    return _norm(s).lower()


def is_committee_track_template(tpl: AssessmentTrackTemplate) -> bool:
    """True when track generates committee_name assignments."""
    if _norm(tpl.code).upper() == "COMMITTEE_EVAL":
        return True
    return _norm(tpl.subject_mode).upper() == "COMMITTEE"


def normalize_committee_config(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize config JSON for persistence.

    Shape:
      { "committees": ["Audit", ...],
        "committee_members": { "Audit": ["a@x.com"] }  # optional
      }
    """
    raw = cfg if isinstance(cfg, dict) else {}
    committees: List[str] = []
    seen_names: Set[str] = set()
    for c in raw.get("committees") or []:
        name = _norm(str(c))
        key = name.lower()
        if name and key not in seen_names:
            seen_names.add(key)
            committees.append(name)

    committee_members: Dict[str, List[str]] = {}
    raw_members = raw.get("committee_members")
    if isinstance(raw_members, dict):
        for cname, emails in raw_members.items():
            cn = _norm(str(cname))
            if not cn:
                continue
            if not isinstance(emails, list):
                continue
            cleaned: List[str] = []
            seen_emails: Set[str] = set()
            for e in emails:
                en = _email_norm(str(e))
                if en and en not in seen_emails:
                    seen_emails.add(en)
                    cleaned.append(en)
            if cleaned:
                committee_members[cn] = cleaned

    out: Dict[str, Any] = {"committees": committees}
    if committee_members:
        out["committee_members"] = committee_members
    if bool(raw.get("exclude_subject_from_respondents")):
        out["exclude_subject_from_respondents"] = True
    return out


def validate_committee_config(
    cfg: Dict[str, Any],
    *,
    enabled: bool,
    known_participant_emails: Set[str],
) -> None:
    """
    Raise ValueError when enabled committee track config is invalid.
    """
    if not enabled:
        return

    committees = cfg.get("committees") or []
    if not committees:
        raise ValueError(
            "Committee evaluation requires at least one committee name "
            "(config.committees)."
        )

    committee_members = cfg.get("committee_members") or {}
    if committee_members and not isinstance(committee_members, dict):
        raise ValueError("committee_members must be an object mapping committee name to email lists.")

    for cname, emails in committee_members.items():
        if not isinstance(emails, list):
            raise ValueError(f"committee_members['{cname}'] must be a list of participant emails.")
        for raw_email in emails:
            en = _email_norm(str(raw_email))
            if not en:
                continue
            if en not in known_participant_emails:
                raise ValueError(
                    f"Unknown participant email '{raw_email}' for committee '{cname}'. "
                    "Invite that person to this evaluation first."
                )
