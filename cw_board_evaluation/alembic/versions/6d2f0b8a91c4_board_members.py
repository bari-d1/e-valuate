"""board_members

Organisation-level board members with sourced profile facts, committee
memberships, director profile documents, and the participant -> board member link.

Revision ID: 6d2f0b8a91c4
Revises: e71c5a09d3b8
Create Date: 2026-10-27 00:03:39.560180

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6d2f0b8a91c4'
down_revision: Union[str, Sequence[str], None] = 'e71c5a09d3b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('board_members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('organisation_id', sa.UUID(), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('display_code', sa.String(length=32), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('profile_status', sa.String(length=16), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('profile_reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("profile_status IN ('draft', 'reviewed')", name='ck_board_members_profile_status'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_board_members_organisation', 'board_members', ['organisation_id'], unique=False)
    op.create_index('uq_board_members_org_display_code', 'board_members', ['organisation_id', 'display_code'], unique=True, postgresql_where=sa.text('display_code IS NOT NULL'))
    op.create_index('uq_board_members_org_email', 'board_members', ['organisation_id', sa.literal_column('lower(email)')], unique=True, postgresql_where=sa.text('email IS NOT NULL'))
    op.create_table('board_member_facts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('board_member_id', sa.UUID(), nullable=False),
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
    sa.CheckConstraint("origin IN ('ai_extraction', 'manual')", name='ck_board_member_facts_origin'),
    sa.CheckConstraint("source IN ('public', 'client', 'consultant')", name='ck_board_member_facts_source'),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name='ck_board_member_facts_status'),
    sa.ForeignKeyConstraint(['board_member_id'], ['board_members.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['source_document_id'], ['org_documents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_board_member_facts_member', 'board_member_facts', ['board_member_id'], unique=False)
    op.create_index('uq_board_member_facts_one_confirmed', 'board_member_facts', ['board_member_id', 'key'], unique=True, postgresql_where=sa.text("status = 'confirmed'"))
    op.create_index('uq_board_member_facts_one_proposed', 'board_member_facts', ['board_member_id', 'key'], unique=True, postgresql_where=sa.text("status = 'proposed'"))
    op.create_table('committee_memberships',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('committee_id', sa.UUID(), nullable=False),
    sa.Column('board_member_id', sa.UUID(), nullable=False),
    sa.Column('membership_role', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('origin', sa.String(length=16), nullable=False),
    sa.Column('matched_name', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("membership_role IN ('member', 'chair')", name='ck_committee_memberships_role'),
    sa.CheckConstraint("origin IN ('name_match', 'manual')", name='ck_committee_memberships_origin'),
    sa.CheckConstraint("source IN ('public', 'client', 'consultant')", name='ck_committee_memberships_source'),
    sa.CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name='ck_committee_memberships_status'),
    sa.ForeignKeyConstraint(['board_member_id'], ['board_members.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['committee_id'], ['org_committees.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('committee_id', 'board_member_id', name='uq_committee_membership')
    )
    op.create_index('ix_committee_memberships_member', 'committee_memberships', ['board_member_id'], unique=False)
    op.add_column('org_documents', sa.Column('board_member_id', sa.UUID(), nullable=True))
    op.create_index('ix_org_documents_board_member', 'org_documents', ['board_member_id'], unique=False)
    op.create_foreign_key('org_documents_board_member_id_fkey', 'org_documents', 'board_members', ['board_member_id'], ['id'], ondelete='SET NULL')
    op.drop_constraint('ck_org_documents_doc_type', 'org_documents', type_='check')
    op.create_check_constraint('ck_org_documents_doc_type', 'org_documents', "doc_type IN ('company_profile', 'board_structure', 'committee_tor', 'governance_policy', 'annual_report', 'public_info', 'other', 'director_profile')")
    op.add_column('participants', sa.Column('board_member_id', sa.UUID(), nullable=True))
    op.create_foreign_key('participants_board_member_id_fkey', 'participants', 'board_members', ['board_member_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('participants_board_member_id_fkey', 'participants', type_='foreignkey')
    op.drop_column('participants', 'board_member_id')
    op.drop_constraint('org_documents_board_member_id_fkey', 'org_documents', type_='foreignkey')
    # Director profile documents fall back to 'other' so the old check can be restored
    op.execute("UPDATE org_documents SET doc_type = 'other' WHERE doc_type = 'director_profile'")
    op.drop_constraint('ck_org_documents_doc_type', 'org_documents', type_='check')
    op.create_check_constraint('ck_org_documents_doc_type', 'org_documents', "doc_type IN ('company_profile', 'board_structure', 'committee_tor', 'governance_policy', 'annual_report', 'public_info', 'other')")
    op.drop_index('ix_org_documents_board_member', table_name='org_documents')
    op.drop_column('org_documents', 'board_member_id')
    op.drop_index('ix_committee_memberships_member', table_name='committee_memberships')
    op.drop_table('committee_memberships')
    op.drop_index('uq_board_member_facts_one_proposed', table_name='board_member_facts', postgresql_where=sa.text("status = 'proposed'"))
    op.drop_index('uq_board_member_facts_one_confirmed', table_name='board_member_facts', postgresql_where=sa.text("status = 'confirmed'"))
    op.drop_index('ix_board_member_facts_member', table_name='board_member_facts')
    op.drop_table('board_member_facts')
    op.drop_index('uq_board_members_org_email', table_name='board_members', postgresql_where=sa.text('email IS NOT NULL'))
    op.drop_index('uq_board_members_org_display_code', table_name='board_members', postgresql_where=sa.text('display_code IS NOT NULL'))
    op.drop_index('ix_board_members_organisation', table_name='board_members')
    op.drop_table('board_members')
