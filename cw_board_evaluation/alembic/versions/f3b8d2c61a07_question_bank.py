"""question_bank

Question bank items (versioned, with respondent and activation rules), their
subject types and suggested/confirmed governance clause links.

Revision ID: f3b8d2c61a07
Revises: c47e9d13a6b2
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f3b8d2c61a07'
down_revision: Union[str, Sequence[str], None] = 'c47e9d13a6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('question_bank_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('answer_type', sa.String(length=16), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('scale', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('theme_code', sa.String(length=64), nullable=False),
    sa.Column('evidence_source_code', sa.String(length=32), nullable=False),
    sa.Column('subject_binding', sa.String(length=32), nullable=False),
    sa.Column('respondent_rule', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('activation_rule', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('known_from', sa.String(length=64), nullable=True),
    sa.Column('known_from_behaviour', sa.String(length=16), nullable=False),
    sa.Column('placeholders', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('guidance', sa.Text(), nullable=True),
    sa.Column('source_refs', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tag_notes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("answer_type IN ('rating', 'yesno', 'comment', 'single_select', 'multi_select')", name='ck_question_bank_items_answer_type'),
    sa.CheckConstraint("known_from_behaviour IN ('skip', 'confirm')", name='ck_question_bank_items_known_from_behaviour'),
    sa.CheckConstraint("status IN ('draft', 'approved', 'retired')", name='ck_question_bank_items_status'),
    sa.CheckConstraint("subject_binding IN ('none', 'self', 'each_subject_instance', 'respondent_committees')", name='ck_question_bank_items_subject_binding'),
    sa.ForeignKeyConstraint(['evidence_source_code'], ['evidence_sources.code'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['theme_code'], ['themes.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'version', name='uq_question_bank_item_code_version')
    )
    op.create_index('ix_question_bank_items_code', 'question_bank_items', ['code'], unique=False)
    op.create_index('ix_question_bank_items_status', 'question_bank_items', ['status'], unique=False)
    op.create_table('question_bank_item_subject_types',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('subject_type_code', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['question_bank_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_type_code'], ['subject_types.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('item_id', 'subject_type_code')
    )
    op.create_index('ix_question_bank_item_subject_types_subject_type', 'question_bank_item_subject_types', ['subject_type_code'], unique=False)
    op.create_table('question_bank_item_clauses',
    sa.Column('item_id', sa.UUID(), nullable=False),
    sa.Column('clause_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.CheckConstraint("status IN ('suggested', 'confirmed')", name='ck_question_bank_item_clauses_status'),
    sa.ForeignKeyConstraint(['clause_id'], ['governance_clauses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['question_bank_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('item_id', 'clause_id')
    )
    op.create_index('ix_question_bank_item_clauses_clause', 'question_bank_item_clauses', ['clause_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_question_bank_item_clauses_clause', table_name='question_bank_item_clauses')
    op.drop_table('question_bank_item_clauses')
    op.drop_index('ix_question_bank_item_subject_types_subject_type', table_name='question_bank_item_subject_types')
    op.drop_table('question_bank_item_subject_types')
    op.drop_index('ix_question_bank_items_status', table_name='question_bank_items')
    op.drop_index('ix_question_bank_items_code', table_name='question_bank_items')
    op.drop_table('question_bank_items')
