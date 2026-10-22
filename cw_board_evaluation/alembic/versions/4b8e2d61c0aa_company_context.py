"""company_context

Organisations (company profile reused across evaluations): documents, sourced
profile facts, committees, governance codes; new evaluation fields, scope
subject types and context snapshots. tenant_name/sector/regulators are kept.

Revision ID: 4b8e2d61c0aa
Revises: 77f8a9c3e317
Create Date: 2026-10-22 13:46:49.513583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4b8e2d61c0aa'
down_revision: Union[str, Sequence[str], None] = '77f8a9c3e317'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('organisations',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('sector_key', sa.String(length=64), nullable=True),
    sa.Column('sector_sub_type', sa.String(length=64), nullable=True),
    sa.Column('country', sa.String(length=8), nullable=False),
    sa.Column('profile_status', sa.String(length=16), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('profile_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("profile_status IN ('draft', 'reviewed')", name='ck_organisations_profile_status'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_organisations_name', 'organisations', ['name'], unique=False)
    op.create_table('org_documents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organisation_id', sa.UUID(), nullable=False),
    sa.Column('doc_type', sa.String(length=32), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=127), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('extracted_text', sa.Text(), nullable=True),
    sa.Column('extraction_status', sa.String(length=16), nullable=False),
    sa.Column('extraction_error', sa.Text(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("doc_type IN ('company_profile', 'board_structure', 'committee_tor', 'governance_policy', 'annual_report', 'public_info', 'other')", name='ck_org_documents_doc_type'),
    sa.CheckConstraint("extraction_status IN ('pending', 'done', 'failed')", name='ck_org_documents_extraction_status'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key', name='uq_org_documents_storage_key')
    )
    op.create_index('ix_org_documents_organisation', 'org_documents', ['organisation_id'], unique=False)
    op.create_table('organisation_governance_codes',
    sa.Column('organisation_id', sa.UUID(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.CheckConstraint("source IN ('sector_default', 'manual')", name='ck_organisation_governance_codes_source'),
    sa.ForeignKeyConstraint(['code'], ['governance_codes.code'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('organisation_id', 'code')
    )
    op.create_table('evaluation_context_snapshots',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('committees', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('document_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('governance_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_evaluation_context_snapshots_evaluation', 'evaluation_context_snapshots', ['evaluation_id', 'created_at'], unique=False)
    op.create_table('evaluation_scope_subject_types',
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('subject_type_code', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subject_type_code'], ['subject_types.code'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('evaluation_id', 'subject_type_code')
    )
    op.create_table('org_committees',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organisation_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('committee_type', sa.String(length=16), nullable=False),
    sa.Column('chair_name', sa.String(length=255), nullable=True),
    sa.Column('member_names', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('terms_of_reference_document_id', sa.UUID(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('source_document_id', sa.UUID(), nullable=True),
    sa.Column('source_excerpt', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("committee_type IN ('audit', 'risk', 'remuneration', 'nomination', 'finance', 'governance', 'other')", name='ck_org_committees_type'),
    sa.CheckConstraint("origin IN ('ai_extraction', 'manual')", name='ck_org_committees_origin'),
    sa.CheckConstraint("source IN ('public', 'client', 'consultant')", name='ck_org_committees_source'),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name='ck_org_committees_status'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['org_documents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['terms_of_reference_document_id'], ['org_documents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_org_committees_organisation', 'org_committees', ['organisation_id'], unique=False)
    op.create_table('organisation_facts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organisation_id', sa.UUID(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('source_document_id', sa.UUID(), nullable=True),
    sa.Column('source_excerpt', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("origin IN ('ai_extraction', 'manual')", name='ck_organisation_facts_origin'),
    sa.CheckConstraint("source IN ('public', 'client', 'consultant')", name='ck_organisation_facts_source'),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name='ck_organisation_facts_status'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['org_documents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_organisation_facts_organisation', 'organisation_facts', ['organisation_id'], unique=False)
    op.create_index('uq_organisation_facts_one_confirmed', 'organisation_facts', ['organisation_id', 'key'], unique=True, postgresql_where=sa.text("status = 'confirmed'"))
    op.create_index('uq_organisation_facts_one_proposed', 'organisation_facts', ['organisation_id', 'key'], unique=True, postgresql_where=sa.text("status = 'proposed'"))
    op.add_column('evaluations', sa.Column('organisation_id', sa.UUID(), nullable=True))
    op.add_column('evaluations', sa.Column('name', sa.String(length=255), nullable=True))
    op.add_column('evaluations', sa.Column('review_period_start', sa.Date(), nullable=True))
    op.add_column('evaluations', sa.Column('review_period_end', sa.Date(), nullable=True))
    op.add_column('evaluations', sa.Column('deadline', sa.Date(), nullable=True))
    op.add_column('evaluations', sa.Column('brief', sa.Text(), nullable=True))
    op.add_column('evaluations', sa.Column('status', sa.String(length=16), server_default='draft', nullable=False))
    op.create_index('ix_evaluations_organisation', 'evaluations', ['organisation_id'], unique=False)
    op.create_foreign_key('evaluations_organisation_id_fkey', 'evaluations', 'organisations', ['organisation_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint('ck_evaluations_status', 'evaluations', "status IN ('draft', 'in_review', 'live', 'closed')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_evaluations_status', 'evaluations', type_='check')
    op.drop_constraint('evaluations_organisation_id_fkey', 'evaluations', type_='foreignkey')
    op.drop_index('ix_evaluations_organisation', table_name='evaluations')
    op.drop_column('evaluations', 'status')
    op.drop_column('evaluations', 'brief')
    op.drop_column('evaluations', 'deadline')
    op.drop_column('evaluations', 'review_period_end')
    op.drop_column('evaluations', 'review_period_start')
    op.drop_column('evaluations', 'name')
    op.drop_column('evaluations', 'organisation_id')
    op.drop_index('uq_organisation_facts_one_proposed', table_name='organisation_facts', postgresql_where=sa.text("status = 'proposed'"))
    op.drop_index('uq_organisation_facts_one_confirmed', table_name='organisation_facts', postgresql_where=sa.text("status = 'confirmed'"))
    op.drop_index('ix_organisation_facts_organisation', table_name='organisation_facts')
    op.drop_table('organisation_facts')
    op.drop_index('ix_org_committees_organisation', table_name='org_committees')
    op.drop_table('org_committees')
    op.drop_table('evaluation_scope_subject_types')
    op.drop_index('ix_evaluation_context_snapshots_evaluation', table_name='evaluation_context_snapshots')
    op.drop_table('evaluation_context_snapshots')
    op.drop_table('organisation_governance_codes')
    op.drop_index('ix_org_documents_organisation', table_name='org_documents')
    op.drop_table('org_documents')
    op.drop_index('ix_organisations_name', table_name='organisations')
    op.drop_table('organisations')
