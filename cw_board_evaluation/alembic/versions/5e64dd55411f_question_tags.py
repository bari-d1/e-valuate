"""question_tags

Optional taxonomy tags on questions: theme_code, evidence_source_code, and a
question_subject_types join table. Question.dimension is not touched.

Revision ID: 5e64dd55411f
Revises: b901df6d51e9
Create Date: 2026-10-22 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5e64dd55411f'
down_revision: Union[str, Sequence[str], None] = 'b901df6d51e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('questions', sa.Column('theme_code', sa.String(length=64), nullable=True))
    op.add_column('questions', sa.Column('evidence_source_code', sa.String(length=32), nullable=True))
    op.create_foreign_key(
        'questions_theme_code_fkey', 'questions', 'themes', ['theme_code'], ['code'], ondelete='RESTRICT'
    )
    op.create_foreign_key(
        'questions_evidence_source_code_fkey', 'questions', 'evidence_sources',
        ['evidence_source_code'], ['code'], ondelete='RESTRICT',
    )
    op.create_index('ix_questions_theme', 'questions', ['theme_code'], unique=False)
    op.create_index('ix_questions_evidence_source', 'questions', ['evidence_source_code'], unique=False)

    op.create_table('question_subject_types',
    sa.Column('question_id', sa.UUID(), nullable=False),
    sa.Column('subject_type_code', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_type_code'], ['subject_types.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('question_id', 'subject_type_code')
    )
    op.create_index(
        'ix_question_subject_types_subject_type', 'question_subject_types', ['subject_type_code'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_question_subject_types_subject_type', table_name='question_subject_types')
    op.drop_table('question_subject_types')
    op.drop_index('ix_questions_evidence_source', table_name='questions')
    op.drop_index('ix_questions_theme', table_name='questions')
    op.drop_constraint('questions_evidence_source_code_fkey', 'questions', type_='foreignkey')
    op.drop_constraint('questions_theme_code_fkey', 'questions', type_='foreignkey')
    op.drop_column('questions', 'evidence_source_code')
    op.drop_column('questions', 'theme_code')
