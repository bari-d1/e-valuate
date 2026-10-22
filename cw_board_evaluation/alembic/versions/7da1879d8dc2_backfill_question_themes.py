"""backfill_question_themes

Data migration: set questions.theme_code from the legacy free-text
questions.dimension. Matching is trimmed and case-insensitive; any other
dimension is left NULL. Subject types and evidence sources are not backfilled
(there isn't enough information to do it reliably).

Downgrade clears only the values this migration would have set, so tags added
later through the API on other questions are kept.

Frozen copy of app.domain.taxonomy.DIMENSION_TO_THEME.

Revision ID: 7da1879d8dc2
Revises: 5e64dd55411f
Create Date: 2026-10-22 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7da1879d8dc2'
down_revision: Union[str, Sequence[str], None] = '5e64dd55411f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DIMENSION_TO_THEME = {
    "Board Composition": "BOARD_COMPOSITION",
    "Risk Oversight": "RISK_MONITORING",
    "Strategy Oversight": "STRATEGY",
    "Board Culture & Dynamics": "BOARD_DYNAMICS",
    "Audit & Assurance": "AUDIT_ASSURANCE",
    "Remuneration & Nomination": "REMUNERATION_NOMINATION",
    "Stakeholder & Stakeholder Governance": "STAKEHOLDER",
    "Compliance & Ethics": "COMPLIANCE_ETHICS",
    "Management Oversight": "MANAGEMENT_OVERSIGHT",
    "Open Comments": "GENERAL",
}

_SET = sa.text(
    "UPDATE questions SET theme_code = :theme "
    "WHERE theme_code IS NULL AND lower(trim(dimension)) = lower(:dimension)"
)
_CLEAR = sa.text(
    "UPDATE questions SET theme_code = NULL "
    "WHERE theme_code = :theme AND lower(trim(dimension)) = lower(:dimension)"
)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    for dimension, theme in DIMENSION_TO_THEME.items():
        conn.execute(_SET, {"theme": theme, "dimension": dimension})


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    for dimension, theme in DIMENSION_TO_THEME.items():
        conn.execute(_CLEAR, {"theme": theme, "dimension": dimension})
