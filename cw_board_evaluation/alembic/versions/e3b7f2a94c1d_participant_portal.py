"""participant_portal

The participant portal for assembled question sets:
- assessment_assignments: the question set behind an ASSEMBLED assignment (one
  per participant), and when it was opened, last saved, submitted and emailed;
- responses: the full answer as JSON (choices, "don't know", confirm items),
  the subject it is about, and when it was last changed;
- evaluations: participant_notice, shown on the form and in the invite email;
- organisation_facts / board_member_facts: origin "participant" for corrections
  from confirm items. These are always proposed and don't count towards the
  one-proposal-per-key limit, so several participants can correct one fact.

Downgrade deletes participant-origin facts (the old constraints don't allow them).

Revision ID: e3b7f2a94c1d
Revises: c5d2e8a91f40
Create Date: 2026-10-28 15:02:11.208431

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e3b7f2a94c1d'
down_revision: Union[str, Sequence[str], None] = 'c5d2e8a91f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FACT_TABLES = (("organisation_facts", "organisation_id"), ("board_member_facts", "board_member_id"))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evaluations', sa.Column('participant_notice', sa.Text(), nullable=True))

    op.add_column('assessment_assignments', sa.Column('question_set_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_assignments_question_set', 'assessment_assignments', 'participant_question_sets',
                          ['question_set_id'], ['id'], ondelete='SET NULL')
    for col in ('opened_at', 'last_activity_at', 'submitted_at', 'email_sent_at'):
        op.add_column('assessment_assignments', sa.Column(col, sa.DateTime(timezone=True), nullable=True))
    op.create_index('uq_assignment_one_assembled', 'assessment_assignments', ['respondent_participant_id'],
                    unique=True, postgresql_where=sa.text("assignment_type = 'ASSEMBLED'"))

    op.add_column('responses', sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('responses', sa.Column('evaluation_subject_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_responses_evaluation_subject', 'responses', 'evaluation_subjects',
                          ['evaluation_subject_id'], ['id'], ondelete='SET NULL')
    op.add_column('responses', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    for table, owner in FACT_TABLES:
        op.drop_constraint(f'ck_{table}_origin', table, type_='check')
        op.create_check_constraint(f'ck_{table}_origin', table, "origin IN ('ai_extraction', 'manual', 'participant')")
        op.drop_index(f'uq_{table}_one_proposed', table_name=table)
        op.create_index(f'uq_{table}_one_proposed', table, [owner, 'key'], unique=True,
                        postgresql_where=sa.text("status = 'proposed' AND origin <> 'participant'"))


def downgrade() -> None:
    """Downgrade schema."""
    for table, owner in FACT_TABLES:
        op.execute(f"DELETE FROM {table} WHERE origin = 'participant'")
        op.drop_index(f'uq_{table}_one_proposed', table_name=table)
        op.create_index(f'uq_{table}_one_proposed', table, [owner, 'key'], unique=True,
                        postgresql_where=sa.text("status = 'proposed'"))
        op.drop_constraint(f'ck_{table}_origin', table, type_='check')
        op.create_check_constraint(f'ck_{table}_origin', table, "origin IN ('ai_extraction', 'manual')")

    op.drop_column('responses', 'updated_at')
    op.drop_constraint('fk_responses_evaluation_subject', 'responses', type_='foreignkey')
    op.drop_column('responses', 'evaluation_subject_id')
    op.drop_column('responses', 'answer')

    op.drop_index('uq_assignment_one_assembled', table_name='assessment_assignments')
    for col in ('email_sent_at', 'submitted_at', 'last_activity_at', 'opened_at'):
        op.drop_column('assessment_assignments', col)
    op.drop_constraint('fk_assignments_question_set', 'assessment_assignments', type_='foreignkey')
    op.drop_column('assessment_assignments', 'question_set_id')

    op.drop_column('evaluations', 'participant_notice')
