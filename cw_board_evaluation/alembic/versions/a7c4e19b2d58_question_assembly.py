"""question_assembly

Per-participant assembled questions on the existing questions table, assembly runs,
participant question sets, suggestion decisions, bank item priority and evaluation options.

The unique (template_code, version, text) constraint becomes a partial unique index on legacy
questions only (participant_id IS NULL): assembled sets legitimately repeat text.

Revision ID: a7c4e19b2d58
Revises: f3b8d2c61a07
Create Date: 2026-10-27 16:13:21.028215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c4e19b2d58'
down_revision: Union[str, Sequence[str], None] = 'f3b8d2c61a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('assembly_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('participant_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('reset', sa.Boolean(), nullable=False),
    sa.Column('include_drafts', sa.Boolean(), nullable=False),
    sa.Column('ai_enabled', sa.Boolean(), nullable=False),
    sa.Column('snapshot_id', sa.UUID(), nullable=True),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rater_warnings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('requested_by', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name='ck_assembly_runs_status'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['snapshot_id'], ['evaluation_context_snapshots.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_assembly_runs_evaluation', 'assembly_runs', ['evaluation_id', 'created_at'], unique=False)
    op.create_table('participant_question_sets',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('assembly_run_id', sa.UUID(), nullable=True),
    sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('estimated_minutes', sa.Integer(), nullable=True),
    sa.Column('override_reason', sa.Text(), nullable=True),
    sa.Column('approved_by', sa.String(length=255), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'approved', 'locked')", name='ck_participant_question_sets_status'),
    sa.ForeignKeyConstraint(['assembly_run_id'], ['assembly_runs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('participant_id', name='uq_participant_question_set_participant')
    )
    op.create_index('ix_participant_question_sets_evaluation', 'participant_question_sets', ['evaluation_id'], unique=False)
    op.create_table('question_suggestion_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('question_id', sa.UUID(), nullable=True),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=True),
    sa.Column('bank_item_id', sa.UUID(), nullable=True),
    sa.Column('bank_item_code', sa.String(length=32), nullable=True),
    sa.Column('bank_item_version', sa.Integer(), nullable=True),
    sa.Column('decision', sa.String(length=16), nullable=False),
    sa.Column('bank_text', sa.Text(), nullable=True),
    sa.Column('ai_text', sa.Text(), nullable=True),
    sa.Column('final_text', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.String(length=255), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision IN ('use_bank', 'use_ai', 'edit', 'accept_new', 'reject_new')", name='ck_question_suggestion_decisions_decision'),
    sa.ForeignKeyConstraint(['bank_item_id'], ['question_bank_items.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_question_suggestion_decisions_bank_item', 'question_suggestion_decisions', ['bank_item_code'], unique=False)
    op.create_index('ix_question_suggestion_decisions_evaluation', 'question_suggestion_decisions', ['evaluation_id'], unique=False)
    op.add_column('evaluations', sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.add_column('question_bank_items', sa.Column('priority', sa.String(length=16), server_default='standard', nullable=False))
    op.add_column('questions', sa.Column('evaluation_id', sa.String(length=64), nullable=True))
    op.add_column('questions', sa.Column('participant_id', sa.UUID(), nullable=True))
    op.add_column('questions', sa.Column('bank_item_id', sa.UUID(), nullable=True))
    op.add_column('questions', sa.Column('bank_item_version', sa.Integer(), nullable=True))
    op.add_column('questions', sa.Column('evaluation_subject_id', sa.UUID(), nullable=True))
    op.add_column('questions', sa.Column('section', sa.String(length=16), nullable=True))
    op.add_column('questions', sa.Column('sort_order', sa.Integer(), nullable=True))
    op.add_column('questions', sa.Column('status', sa.String(length=16), nullable=True))
    op.add_column('questions', sa.Column('bank_text', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('ai_text', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('ai_reason', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('text_source', sa.String(length=24), nullable=True))
    op.add_column('questions', sa.Column('suggestion_status', sa.String(length=16), nullable=True))
    op.add_column('questions', sa.Column('ai_fact_key', sa.String(length=64), nullable=True))
    op.add_column('questions', sa.Column('depends_on_question_id', sa.UUID(), nullable=True))
    op.add_column('questions', sa.Column('show_if', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('questions', sa.Column('confirm_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('questions', sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('questions', sa.Column('scale', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.drop_constraint('uq_question_template_version_text', 'questions', type_='unique')
    op.create_index('uq_question_template_version_text', 'questions', ['template_code', 'version', 'text'], unique=True, postgresql_where=sa.text('participant_id IS NULL'))
    op.create_index('ix_questions_evaluation', 'questions', ['evaluation_id'], unique=False)
    op.create_index('ix_questions_participant', 'questions', ['participant_id'], unique=False)
    op.create_foreign_key('fk_questions_evaluation', 'questions', 'evaluations', ['evaluation_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_questions_bank_item', 'questions', 'question_bank_items', ['bank_item_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_questions_participant', 'questions', 'participants', ['participant_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_questions_evaluation_subject', 'questions', 'evaluation_subjects', ['evaluation_subject_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_questions_depends_on', 'questions', 'questions', ['depends_on_question_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint(
        'ck_questions_section', 'questions',
        "section IS NULL OR section IN ('board', 'committees', 'colleagues', 'yourself', 'confirm', 'additional')",
    )
    op.create_check_constraint('ck_questions_status', 'questions', "status IS NULL OR status IN ('draft', 'approved', 'locked')")
    op.create_check_constraint(
        'ck_questions_text_source', 'questions',
        "text_source IS NULL OR text_source IN ('bank', 'ai_tailored', 'ai_new', 'consultant_edited')",
    )
    op.create_check_constraint('ck_question_bank_items_priority', 'question_bank_items', "priority IN ('core', 'standard', 'optional')")


def downgrade() -> None:
    """Downgrade schema. Assembled questions (and their responses) are deleted: the old schema can't hold them."""
    op.execute("DELETE FROM questions WHERE participant_id IS NOT NULL")
    op.drop_constraint('ck_question_bank_items_priority', 'question_bank_items', type_='check')
    op.drop_constraint('ck_questions_text_source', 'questions', type_='check')
    op.drop_constraint('ck_questions_status', 'questions', type_='check')
    op.drop_constraint('ck_questions_section', 'questions', type_='check')
    op.drop_constraint('fk_questions_evaluation', 'questions', type_='foreignkey')
    op.drop_constraint('fk_questions_bank_item', 'questions', type_='foreignkey')
    op.drop_constraint('fk_questions_participant', 'questions', type_='foreignkey')
    op.drop_constraint('fk_questions_evaluation_subject', 'questions', type_='foreignkey')
    op.drop_constraint('fk_questions_depends_on', 'questions', type_='foreignkey')
    op.drop_index('ix_questions_participant', table_name='questions')
    op.drop_index('ix_questions_evaluation', table_name='questions')
    op.drop_index('uq_question_template_version_text', table_name='questions', postgresql_where=sa.text('participant_id IS NULL'))
    op.create_unique_constraint('uq_question_template_version_text', 'questions', ['template_code', 'version', 'text'])
    op.drop_column('questions', 'scale')
    op.drop_column('questions', 'options')
    op.drop_column('questions', 'confirm_value')
    op.drop_column('questions', 'show_if')
    op.drop_column('questions', 'depends_on_question_id')
    op.drop_column('questions', 'ai_fact_key')
    op.drop_column('questions', 'suggestion_status')
    op.drop_column('questions', 'text_source')
    op.drop_column('questions', 'ai_reason')
    op.drop_column('questions', 'ai_text')
    op.drop_column('questions', 'bank_text')
    op.drop_column('questions', 'status')
    op.drop_column('questions', 'sort_order')
    op.drop_column('questions', 'section')
    op.drop_column('questions', 'evaluation_subject_id')
    op.drop_column('questions', 'bank_item_version')
    op.drop_column('questions', 'bank_item_id')
    op.drop_column('questions', 'participant_id')
    op.drop_column('questions', 'evaluation_id')
    op.drop_column('question_bank_items', 'priority')
    op.drop_column('evaluations', 'options')
    op.drop_index('ix_question_suggestion_decisions_evaluation', table_name='question_suggestion_decisions')
    op.drop_index('ix_question_suggestion_decisions_bank_item', table_name='question_suggestion_decisions')
    op.drop_table('question_suggestion_decisions')
    op.drop_index('ix_participant_question_sets_evaluation', table_name='participant_question_sets')
    op.drop_table('participant_question_sets')
    op.drop_index('ix_assembly_runs_evaluation', table_name='assembly_runs')
    op.drop_table('assembly_runs')
