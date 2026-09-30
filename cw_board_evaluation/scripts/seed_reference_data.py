"""
Seed global assessment_track_templates (idempotent by code).
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from sqlalchemy import select
from app.db.models import AssessmentTrackTemplate
from app.db.session import SessionLocal

TRACK_TEMPLATES = [
    {"code": "BOARD_AS_WHOLE", "name": "Board as a whole", "description": "Collective assessment of the full board.", "assignment_type": "BOARD_AS_WHOLE", "subject_mode": "NONE", "subject_role": None, "respondent_rule": {"mode": "ALL"}},
    {"code": "CHAIR_EVAL", "name": "Chair evaluation", "description": "INED-only raters evaluate the Chair.", "assignment_type": "CHAIR_EVAL", "subject_mode": "PARTICIPANT_ROLE", "subject_role": "Chair", "respondent_rule": {"mode": "ROLE_IN", "roles": ["INED"]}},
    {"code": "DIRECTOR_SELF", "name": "Director self-assessment", "description": "Each director assesses themselves.", "assignment_type": "DIRECTOR_SELF", "subject_mode": "PARTICIPANT_SELF", "subject_role": None, "respondent_rule": {"mode": "ALL"}},
    {"code": "DIRECTOR_PEER", "name": "Director peer assessment", "description": "Directors rate each other.", "assignment_type": "DIRECTOR_PEER", "subject_mode": "PARTICIPANT_EACH", "subject_role": None, "respondent_rule": {"mode": "ALL"}},
    {"code": "COMMITTEE_EVAL", "name": "Committee evaluation", "description": "Committee-level assessments.", "assignment_type": "COMMITTEE_EVAL", "subject_mode": "COMMITTEE", "subject_role": None, "respondent_rule": {"mode": "ALL"}},
    {"code": "GOV_AUDIT", "name": "Governance / audit", "description": "Governance and audit oversight track.", "assignment_type": "GOV_AUDIT", "subject_mode": "NONE", "subject_role": None, "respondent_rule": {"mode": "ALL"}},
]

def main():
    created = updated = 0
    db = SessionLocal()
    try:
        for spec in TRACK_TEMPLATES:
            code = spec["code"]
            existing = db.execute(select(AssessmentTrackTemplate).where(AssessmentTrackTemplate.code == code)).scalar_one_or_none()
            if existing:
                for k, v in spec.items():
                    setattr(existing, k, v)
                existing.default_template_code = "DEFAULT"
                existing.default_version = 1
                existing.active = 1
                updated += 1
            else:
                db.add(AssessmentTrackTemplate(id=uuid.uuid4(), default_template_code="DEFAULT", default_version=1, active=1, **spec))
                created += 1
        db.commit()
    finally:
        db.close()
    print(f"Track templates: {created} created, {updated} updated.")

if __name__ == "__main__":
    main()
