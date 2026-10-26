"""sector_code_defaults

Seeds which governance codes apply by default to each sector. Idempotent;
frozen copy of app.domain.governance.SECTOR_CODE_DEFAULTS.

Revision ID: 77f8a9c3e317
Revises: 9c93e7123f6a
Create Date: 2026-10-22 15:20:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '77f8a9c3e317'
down_revision: Union[str, Sequence[str], None] = '9c93e7123f6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (sector, sub_type, code); sub_type None is the sector's default list
SECTOR_CODE_DEFAULTS = [('insurance', None, 'NCCG_2018'),
 ('insurance', None, 'NAICOM_2021'),
 ('banking', None, 'NCCG_2018'),
 ('banking', None, 'CBN_BANKS_2023'),
 ('banking', 'microfinance', 'NCCG_2018'),
 ('banking', 'microfinance', 'CBN_MFB_2018'),
 ('pension', None, 'NCCG_2018'),
 ('pension', None, 'PENCOM_2025'),
 ('telecommunications', None, 'NCCG_2018'),
 ('telecommunications', None, 'NCC_2025'),
 ('sme', None, 'SME_2024'),
 ('finance', None, 'NCCG_2018')]

_INSERT = sa.text(
    "INSERT INTO sector_code_defaults (id, sector, sub_type, code) "
    "VALUES (:id, :sector, :sub_type, :code) ON CONFLICT ON CONSTRAINT uq_sector_code_default DO NOTHING"
)
_DELETE = sa.text(
    "DELETE FROM sector_code_defaults "
    "WHERE sector = :sector AND sub_type IS NOT DISTINCT FROM :sub_type AND code = :code"
)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    for sector, sub_type, code in SECTOR_CODE_DEFAULTS:
        conn.execute(_INSERT, {"id": uuid.uuid4(), "sector": sector, "sub_type": sub_type, "code": code})


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    for sector, sub_type, code in SECTOR_CODE_DEFAULTS:
        conn.execute(_DELETE, {"sector": sector, "sub_type": sub_type, "code": code})
