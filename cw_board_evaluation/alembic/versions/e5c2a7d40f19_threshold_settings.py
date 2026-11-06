"""threshold_settings

Draft-signal thresholds (strength, concern, self/peer gap) are configuration the
client approves, not methodology (spec v1.1). New runs record the thresholds they
used in analysis_runs.settings["thresholds"], with settings["thresholds_status"]
"unapproved". Runs made before this used the defaults below, so they get those
recorded, also as unapproved. No schema change: settings is JSONB.

Revision ID: e5c2a7d40f19
Revises: d1a6f0c3e8b2
Create Date: 2026-11-06 12:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e5c2a7d40f19'
down_revision: Union[str, Sequence[str], None] = 'd1a6f0c3e8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The values app.domain.analysis_rules had when these runs were made (frozen here on purpose)
DEFAULTS = {"theme_strength_mean": 4.2, "item_strength_mean": 4.5, "concern_mean": 2.5, "self_peer_gap": 1.0}


def upgrade() -> None:
    """Upgrade schema."""
    op.get_bind().execute(sa.text(
        "UPDATE analysis_runs SET settings = settings || jsonb_build_object("
        "'thresholds', CAST(:defaults AS jsonb), 'thresholds_status', 'unapproved') "
        "WHERE NOT settings ? 'thresholds'"), {"defaults": json.dumps(DEFAULTS)})


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE analysis_runs SET settings = settings - 'thresholds' - 'thresholds_status'")
