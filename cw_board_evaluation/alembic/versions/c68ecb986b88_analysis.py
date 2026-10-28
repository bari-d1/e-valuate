"""analysis

Analysis of assembled evaluations:
- analysis_runs: one run of the analysis (settings, inputs, results); immutable once
  done, re-runs make new runs;
- analysis_evidence: one row per answer a run used, the source every number and
  finding traces back to (respondent category and a per-run pseudonym, never names);
- findings (+ finding_evidence, finding_clauses) and conclusions: drafts from rules,
  AI or the consultant, and the consultant's decisions on them;
- question_bank_items.expected_answer: the answer good practice expects on factual
  yes/no items, for compliance checks. Set here for the clear-cut items already loaded
  (the bank fixture carries the same values); left empty where it isn't clear.

Revision ID: c68ecb986b88
Revises: f4a9c3d7b215
Create Date: 2026-10-28 15:22:49.634610

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c68ecb986b88'
down_revision: Union[str, Sequence[str], None] = 'f4a9c3d7b215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Factual yes/no items linked to a governance clause where the expected answer is clear-cut
EXPECTED_YES = ['BOARD-STR-03', 'SEC-01', 'SEC-24', 'SEC-29', 'SEC-30', 'SEC-32', 'SEC-35', 'SEC-37', 'SEC-41', 'SEC-44', 'SEC-48', 'SEC-49', 'SEC-56', 'SEC-58', 'SEC-65', 'COM-CORE-01', 'COM-AUDIT-04', 'EXEC-SELF-01', 'EXEC-SELF-05', 'CHAIR-SELF-05']
EXPECTED_NO = ['CHAIR-SELF-01', 'CHAIR-SELF-02', 'CEO-SELF-01', 'CEO-SELF-02', 'INED-IND-02', 'INED-IND-03', 'INED-IND-04', 'INED-IND-05', 'INED-IND-06', 'INED-IND-07', 'INED-IND-08', 'INED-IND-09']


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('analysis_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('inputs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_by', sa.String(length=255), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('running', 'done', 'failed')", name='ck_analysis_runs_status'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analysis_runs_evaluation', 'analysis_runs', ['evaluation_id', 'created_at'], unique=False)
    op.create_table('conclusions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('evaluation_subject_id', sa.UUID(), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=True),
    sa.Column('no_findings', sa.Boolean(), nullable=False),
    sa.Column('edited_by', sa.String(length=255), nullable=True),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("origin IN ('computed', 'ai', 'consultant')", name='ck_conclusions_origin'),
    sa.CheckConstraint("status IN ('draft', 'accepted', 'edited', 'rejected')", name='ck_conclusions_status'),
    sa.ForeignKeyConstraint(['evaluation_subject_id'], ['evaluation_subjects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'evaluation_subject_id', name='uq_conclusions_run_subject', postgresql_nulls_not_distinct=True)
    )
    op.create_table('findings',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('evaluation_subject_id', sa.UUID(), nullable=True),
    sa.Column('theme_code', sa.String(length=64), nullable=True),
    sa.Column('bank_item_code', sa.String(length=32), nullable=True),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('support', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('original_text', sa.Text(), nullable=True),
    sa.Column('rule', sa.String(length=64), nullable=True),
    sa.Column('edited_by', sa.String(length=255), nullable=True),
    sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('strength', 'concern', 'observation', 'compliance_gap', 'self_perception_gap')", name='ck_findings_kind'),
    sa.CheckConstraint("origin IN ('computed', 'ai', 'consultant')", name='ck_findings_origin'),
    sa.CheckConstraint("status IN ('draft', 'accepted', 'edited', 'rejected')", name='ck_findings_status'),
    sa.CheckConstraint("support IN ('strong', 'moderate', 'limited', 'conflicting')", name='ck_findings_support'),
    sa.ForeignKeyConstraint(['evaluation_subject_id'], ['evaluation_subjects.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_findings_run_subject', 'findings', ['run_id', 'evaluation_subject_id'], unique=False)
    op.create_table('finding_clauses',
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('clause_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['clause_id'], ['governance_clauses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('finding_id', 'clause_id')
    )
    op.create_table('analysis_evidence',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('response_id', sa.UUID(), nullable=True),
    sa.Column('question_id', sa.UUID(), nullable=True),
    sa.Column('evaluation_subject_id', sa.UUID(), nullable=True),
    sa.Column('theme_code', sa.String(length=64), nullable=True),
    sa.Column('evidence_source_code', sa.String(length=32), nullable=True),
    sa.Column('bank_item_code', sa.String(length=32), nullable=True),
    sa.Column('answer_type', sa.String(length=16), nullable=False),
    sa.Column('question_text', sa.Text(), nullable=False),
    sa.Column('respondent_category', sa.String(length=32), nullable=False),
    sa.Column('respondent_ref', sa.String(length=16), nullable=False),
    sa.Column('is_self', sa.Boolean(), nullable=False),
    sa.Column('in_progress', sa.Boolean(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['evaluation_subject_id'], ['evaluation_subjects.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['response_id'], ['responses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_analysis_evidence_run_subject', 'analysis_evidence', ['run_id', 'evaluation_subject_id'], unique=False)
    op.create_table('finding_evidence',
    sa.Column('finding_id', sa.UUID(), nullable=False),
    sa.Column('evidence_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['evidence_id'], ['analysis_evidence.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['finding_id'], ['findings.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('finding_id', 'evidence_id')
    )
    op.add_column('question_bank_items', sa.Column('expected_answer', sa.String(length=8), nullable=True))
    op.create_check_constraint('ck_question_bank_items_expected_answer', 'question_bank_items',
                               "expected_answer IS NULL OR expected_answer IN ('yes', 'no')")
    items = sa.table('question_bank_items', sa.column('code', sa.String), sa.column('answer_type', sa.String),
                     sa.column('expected_answer', sa.String))
    for answer, codes in (('yes', EXPECTED_YES), ('no', EXPECTED_NO)):
        op.execute(items.update().where(items.c.code.in_(codes), items.c.answer_type == 'yesno')
                   .values(expected_answer=answer))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_question_bank_items_expected_answer', 'question_bank_items', type_='check')
    op.drop_column('question_bank_items', 'expected_answer')
    op.drop_table('finding_evidence')
    op.drop_index('ix_analysis_evidence_run_subject', table_name='analysis_evidence')
    op.drop_table('analysis_evidence')
    op.drop_table('finding_clauses')
    op.drop_index('ix_findings_run_subject', table_name='findings')
    op.drop_table('findings')
    op.drop_table('conclusions')
    op.drop_index('ix_analysis_runs_evaluation', table_name='analysis_runs')
    op.drop_table('analysis_runs')
