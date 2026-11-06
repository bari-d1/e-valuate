"""practice_gap

Findings drawn from a factual yes/no answer that differs from the expected answer
are self-reported practice to verify, not compliance conclusions (methodology spec
v1.1: a regulatory obligation is never inferred from a questionnaire response alone).
The kind compliance_gap becomes practice_gap and the rule compliance_shortfall
becomes practice_differs. Statements already written are left as they are: the
consultant may have edited them, and the kind label now says "unverified".

Revision ID: d1a6f0c3e8b2
Revises: c68ecb986b88
Create Date: 2026-11-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1a6f0c3e8b2'
down_revision: Union[str, Sequence[str], None] = 'c68ecb986b88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KINDS = "'strength', 'concern', 'observation', 'compliance_gap', 'self_perception_gap'"
NEW_KINDS = "'strength', 'concern', 'observation', 'practice_gap', 'self_perception_gap'"


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_findings_kind', 'findings', type_='check')
    op.execute("UPDATE findings SET kind = 'practice_gap' WHERE kind = 'compliance_gap'")
    op.execute("UPDATE findings SET rule = 'practice_differs' WHERE rule = 'compliance_shortfall'")
    op.create_check_constraint('ck_findings_kind', 'findings', f"kind IN ({NEW_KINDS})")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_findings_kind', 'findings', type_='check')
    op.execute("UPDATE findings SET kind = 'compliance_gap' WHERE kind = 'practice_gap'")
    op.execute("UPDATE findings SET rule = 'compliance_shortfall' WHERE rule = 'practice_differs'")
    op.create_check_constraint('ck_findings_kind', 'findings', f"kind IN ({OLD_KINDS})")
