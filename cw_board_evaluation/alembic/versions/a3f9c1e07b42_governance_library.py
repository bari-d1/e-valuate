"""governance_library

Governance code library: codes (one row per edition), numbered clauses with
hierarchy and cross-code citations, clause subject-type tags, sector defaults,
and the codes each evaluation is assessed against.

Revision ID: a3f9c1e07b42
Revises: cd3b2611fb3d
Create Date: 2026-10-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f9c1e07b42'
down_revision: Union[str, Sequence[str], None] = 'cd3b2611fb3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('governance_codes',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('issuer', sa.String(length=255), nullable=False),
    sa.Column('jurisdiction', sa.String(length=8), nullable=False),
    sa.Column('sector', sa.String(length=64), nullable=True),
    sa.Column('version', sa.String(length=32), nullable=False),
    sa.Column('issued_date', sa.Date(), nullable=True),
    sa.Column('effective_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('supplements_code', sa.String(length=32), nullable=True),
    sa.Column('source_filename', sa.String(length=255), nullable=True),
    sa.Column('clauses_loaded', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.CheckConstraint("status IN ('current', 'historical', 'superseded')", name='ck_governance_codes_status'),
    sa.ForeignKeyConstraint(['supplements_code'], ['governance_codes.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_table('governance_clauses',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('reference', sa.String(length=32), nullable=False),
    sa.Column('parent_id', sa.UUID(), nullable=True),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('heading', sa.String(length=255), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('cites_clause_id', sa.UUID(), nullable=True),
    sa.Column('theme_code', sa.String(length=64), nullable=True),
    sa.CheckConstraint(
        "level IN ('part', 'principle', 'practice', 'section', 'subsection')", name='ck_governance_clauses_level'
    ),
    sa.ForeignKeyConstraint(['cites_clause_id'], ['governance_clauses.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['code'], ['governance_codes.code'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['parent_id'], ['governance_clauses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['theme_code'], ['themes.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', 'reference', name='uq_governance_clause_code_reference')
    )
    op.create_index('ix_governance_clauses_code_sort', 'governance_clauses', ['code', 'sort_order'], unique=False)
    op.create_index('ix_governance_clauses_parent', 'governance_clauses', ['parent_id'], unique=False)
    op.create_index('ix_governance_clauses_theme', 'governance_clauses', ['theme_code'], unique=False)
    op.create_table('governance_clause_subject_types',
    sa.Column('clause_id', sa.UUID(), nullable=False),
    sa.Column('subject_type_code', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['clause_id'], ['governance_clauses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_type_code'], ['subject_types.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('clause_id', 'subject_type_code')
    )
    op.create_index(
        'ix_governance_clause_subject_types_subject_type', 'governance_clause_subject_types',
        ['subject_type_code'], unique=False,
    )
    op.create_table('sector_code_defaults',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('sector', sa.String(length=64), nullable=False),
    sa.Column('sub_type', sa.String(length=64), nullable=True),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['code'], ['governance_codes.code'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint(
        'sector', 'sub_type', 'code', name='uq_sector_code_default', postgresql_nulls_not_distinct=True
    )
    )
    op.create_index('ix_sector_code_defaults_sector', 'sector_code_defaults', ['sector'], unique=False)
    op.create_table('evaluation_governance_codes',
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("source IN ('sector_default', 'manual')", name='ck_evaluation_governance_codes_source'),
    sa.ForeignKeyConstraint(['code'], ['governance_codes.code'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('evaluation_id', 'code')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('evaluation_governance_codes')
    op.drop_index('ix_sector_code_defaults_sector', table_name='sector_code_defaults')
    op.drop_table('sector_code_defaults')
    op.drop_index('ix_governance_clause_subject_types_subject_type', table_name='governance_clause_subject_types')
    op.drop_table('governance_clause_subject_types')
    op.drop_index('ix_governance_clauses_theme', table_name='governance_clauses')
    op.drop_index('ix_governance_clauses_parent', table_name='governance_clauses')
    op.drop_index('ix_governance_clauses_code_sort', table_name='governance_clauses')
    op.drop_table('governance_clauses')
    op.drop_table('governance_codes')
