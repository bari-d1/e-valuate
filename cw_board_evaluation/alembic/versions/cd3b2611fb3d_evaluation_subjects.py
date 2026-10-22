"""evaluation_subjects

Concrete subjects per evaluation (board, committees, people by role).

Revision ID: cd3b2611fb3d
Revises: 7da1879d8dc2
Create Date: 2026-10-22 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cd3b2611fb3d'
down_revision: Union[str, Sequence[str], None] = '7da1879d8dc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('evaluation_subjects',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('subject_type_code', sa.String(length=32), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=True),
    sa.Column('committee_name', sa.String(length=255), nullable=True),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('participant_id IS NULL OR committee_name IS NULL', name='ck_evaluation_subjects_one_target'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_type_code'], ['subject_types.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint(
        'evaluation_id', 'subject_type_code', 'participant_id', 'committee_name',
        name='uq_evaluation_subject', postgresql_nulls_not_distinct=True,
    )
    )
    op.create_index('ix_evaluation_subjects_evaluation', 'evaluation_subjects', ['evaluation_id'], unique=False)
    op.create_index('ix_evaluation_subjects_participant', 'evaluation_subjects', ['participant_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_evaluation_subjects_participant', table_name='evaluation_subjects')
    op.drop_index('ix_evaluation_subjects_evaluation', table_name='evaluation_subjects')
    op.drop_table('evaluation_subjects')
