"""consultant_review

Consultant review of assembled question sets:
- question_set_events: the audit trail of every change to a participant's set
  (who, when, what changed), including set-level actions (approve, reopen, lock);
- questions: status "removed" (kept for audit, left out of the participant's
  form), text_source "consultant_written", and columns for the removal reason,
  the rule reasons the question was included for, and who added it by hand.

Downgrade deletes removed and consultant-written questions (the old constraints
don't allow them) and the audit trail.

Revision ID: c5d2e8a91f40
Revises: a7c4e19b2d58
Create Date: 2026-10-28 09:12:40.511203

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5d2e8a91f40'
down_revision: Union[str, Sequence[str], None] = 'a7c4e19b2d58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIONS = ("use_bank", "use_ai", "edit", "accept_new", "reject_new", "regenerate", "edit_tags", "remove", "restore",
           "add_from_bank", "add_written", "move", "approve", "reopen", "lock")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('question_set_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=True),
    sa.Column('question_set_id', sa.UUID(), nullable=True),
    sa.Column('question_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=24), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("action IN (" + ", ".join(f"'{a}'" for a in ACTIONS) + ")", name='ck_question_set_events_action'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['question_set_id'], ['participant_question_sets.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_question_set_events_evaluation', 'question_set_events', ['evaluation_id', 'created_at'], unique=False)
    op.create_index('ix_question_set_events_participant', 'question_set_events', ['participant_id', 'created_at'], unique=False)

    op.add_column('questions', sa.Column('removed_reason', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('selection_reason', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('added_by', sa.String(length=255), nullable=True))
    op.drop_constraint('ck_questions_status', 'questions', type_='check')
    op.create_check_constraint('ck_questions_status', 'questions',
                               "status IS NULL OR status IN ('draft', 'approved', 'locked', 'removed')")
    op.drop_constraint('ck_questions_text_source', 'questions', type_='check')
    op.create_check_constraint('ck_questions_text_source', 'questions',
                               "text_source IS NULL OR text_source IN ('bank', 'ai_tailored', 'ai_new', "
                               "'consultant_edited', 'consultant_written')")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM questions WHERE status = 'removed' OR text_source = 'consultant_written'")
    op.drop_constraint('ck_questions_text_source', 'questions', type_='check')
    op.create_check_constraint('ck_questions_text_source', 'questions',
                               "text_source IS NULL OR text_source IN ('bank', 'ai_tailored', 'ai_new', 'consultant_edited')")
    op.drop_constraint('ck_questions_status', 'questions', type_='check')
    op.create_check_constraint('ck_questions_status', 'questions',
                               "status IS NULL OR status IN ('draft', 'approved', 'locked')")
    op.drop_column('questions', 'added_by')
    op.drop_column('questions', 'selection_reason')
    op.drop_column('questions', 'removed_reason')
    op.drop_index('ix_question_set_events_participant', table_name='question_set_events')
    op.drop_index('ix_question_set_events_evaluation', table_name='question_set_events')
    op.drop_table('question_set_events')
