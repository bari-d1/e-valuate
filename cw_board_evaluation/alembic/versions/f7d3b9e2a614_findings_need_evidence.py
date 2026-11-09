"""findings_need_evidence

A finding can only be approved (accepted or edited) while at least one piece of
evidence backs it (methodology spec v1.1, acceptance test AT04). findings.note
records why the system changed a finding's status. Findings already approved
without evidence (consultants' own, which were saved as accepted straight away)
go back to draft with a note saying so and what they were, so nothing is lost
silently and the downgrade can put them back.

Revision ID: f7d3b9e2a614
Revises: e5c2a7d40f19
Create Date: 2026-11-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7d3b9e2a614'
down_revision: Union[str, Sequence[str], None] = 'e5c2a7d40f19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTE = ("Moved back to draft when evidence became required for approval (spec v1.1, AT04): "
        "no evidence was linked. Link evidence to approve it again. (was {status})")
UNEVIDENCED = "NOT EXISTS (SELECT 1 FROM finding_evidence fe WHERE fe.finding_id = findings.id)"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('findings', sa.Column('note', sa.Text(), nullable=True))
    for status in ('accepted', 'edited'):
        op.get_bind().execute(sa.text(
            f"UPDATE findings SET status = 'draft', note = :note WHERE status = :status AND {UNEVIDENCED}"),
            {"note": NOTE.format(status=status), "status": status})


def downgrade() -> None:
    """Downgrade schema."""
    for status in ('accepted', 'edited'):
        op.get_bind().execute(sa.text("UPDATE findings SET status = :status WHERE status = 'draft' AND note = :note"),
                              {"note": NOTE.format(status=status), "status": status})
    op.drop_column('findings', 'note')
