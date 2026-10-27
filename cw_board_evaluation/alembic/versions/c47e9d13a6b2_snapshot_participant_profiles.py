"""snapshot_participant_profiles

Context snapshots also record each participant's board member profile
(participants) and, separately, generation_only facts (generation_only) so
analysis code can leave them out.

Revision ID: c47e9d13a6b2
Revises: 8a1e47c2d5f0
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c47e9d13a6b2'
down_revision: Union[str, Sequence[str], None] = '8a1e47c2d5f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evaluation_context_snapshots', sa.Column(
        'participants', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('evaluation_context_snapshots', sa.Column(
        'generation_only', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('evaluation_context_snapshots', 'generation_only')
    op.drop_column('evaluation_context_snapshots', 'participants')
