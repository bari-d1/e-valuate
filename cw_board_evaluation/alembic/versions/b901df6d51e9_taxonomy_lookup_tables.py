"""taxonomy_lookup_tables

Adds subject_types, themes and evidence_sources and seeds them (idempotent:
existing rows are left alone, so names edited later are not overwritten).

The seed data is a frozen copy of app.domain.taxonomy at the time of writing;
migrations must not import application code that may change later.

Revision ID: b901df6d51e9
Revises: 2fb54b7b8545
Create Date: 2026-10-22 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = 'b901df6d51e9'
down_revision: Union[str, Sequence[str], None] = '2fb54b7b8545'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUBJECT_TYPES = [
    ("BOARD", "Board as a whole", "The board as a collective body.", "single"),
    ("CHAIR", "Board chairman", "The chair of the board.", "single"),
    ("MD_CEO", "Managing Director / CEO", "The managing director or chief executive.", "single"),
    ("ED", "Executive director", "An executive director.", "per_person"),
    ("NED", "Non-executive director", "A non-executive director.", "per_person"),
    ("INED", "Independent NED", "An independent non-executive director.", "per_person"),
    ("COMMITTEE", "Board committee", "A committee of the board.", "per_committee"),
    ("COMPANY_SECRETARY", "Company secretary / secretariat", "The company secretary or board secretariat.", "single"),
]

THEMES = [
    ("BOARD_EFFECTIVENESS", "Board effectiveness"),
    ("BOARD_COMPOSITION", "Board composition"),
    ("BOARD_DYNAMICS", "Board dynamics and relationships"),
    ("STRATEGY", "Strategy and business"),
    ("RISK_MONITORING", "Monitoring and risk management"),
    ("AUDIT_ASSURANCE", "Audit and assurance"),
    ("REMUNERATION_NOMINATION", "Remuneration and nomination"),
    ("STAKEHOLDER", "Stakeholder governance"),
    ("COMPLIANCE_ETHICS", "Compliance and ethics"),
    ("MANAGEMENT_OVERSIGHT", "Management oversight"),
    ("INDEPENDENCE", "Independence"),
    ("GENERAL", "General / open comments"),
]

EVIDENCE_SOURCES = [
    ("PERCEPTION", "Perception", "A participant's view of others (peer, whole-board views)."),
    ("ROLE_SELF", "Role self-evidence", "A participant's evidence about their own role."),
    ("ORG_FACT", "Organisational fact", "An organisational or process fact (e.g. from the secretariat)."),
]


def upgrade() -> None:
    """Upgrade schema."""
    subject_types = op.create_table('subject_types',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('cardinality', sa.String(length=16), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Integer(), nullable=False),
    sa.CheckConstraint("cardinality IN ('single', 'per_person', 'per_committee')", name='ck_subject_types_cardinality'),
    sa.PrimaryKeyConstraint('code')
    )
    themes = op.create_table('themes',
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    evidence_sources = op.create_table('evidence_sources',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )

    rows = {
        subject_types: [
            {"code": c, "name": n, "description": d, "cardinality": k, "sort_order": (i + 1) * 10, "active": 1}
            for i, (c, n, d, k) in enumerate(SUBJECT_TYPES)
        ],
        themes: [
            {"code": c, "name": n, "description": None, "sort_order": (i + 1) * 10, "active": 1}
            for i, (c, n) in enumerate(THEMES)
        ],
        evidence_sources: [
            {"code": c, "name": n, "description": d, "sort_order": (i + 1) * 10}
            for i, (c, n, d) in enumerate(EVIDENCE_SOURCES)
        ],
    }
    for table, values in rows.items():
        op.execute(pg_insert(table).values(values).on_conflict_do_nothing(index_elements=["code"]))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('evidence_sources')
    op.drop_table('themes')
    op.drop_table('subject_types')
