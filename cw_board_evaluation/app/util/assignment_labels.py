"""Human-readable labels for assessment assignments (email, hub, consultant UI)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def assignment_link_label(
    item: Dict[str, Any],
    *,
    subject_name: Optional[str] = None,
) -> str:
    """Build a short label for one assignment row."""
    at = str(item.get("assignment_type") or "").strip()
    tc = str(item.get("track_code") or "").strip()
    cn = str(item.get("committee_name") or "").strip()
    parts = [at] if at else []
    if tc and tc != at:
        parts.append(f"({tc})")
    if cn:
        parts.append(f"— {cn}")
    sn = (subject_name or str(item.get("subject_name") or "")).strip()
    if sn:
        parts.append(f"— re {sn}")
    return " ".join(parts) if parts else "Questionnaire"
