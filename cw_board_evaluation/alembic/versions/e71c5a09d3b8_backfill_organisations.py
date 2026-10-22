"""backfill_organisations

Data migration: one organisation per distinct (trimmed) Evaluation.tenant_name,
sector mapped with app.domain.governance.normalize_sector, evaluations linked,
all eight subject types put in scope for each evaluation, and the sector's
default governance codes linked to each organisation.

Evaluation.tenant_name, sector and regulators are NOT changed or dropped.

Idempotent: only evaluations without an organisation are processed, and an
existing organisation with the same name is reused. Downgrade leaves the data
in place (the tables still exist at the previous revision), so
upgrade -> downgrade -> upgrade creates no duplicates.

Sectors that don't normalise are logged and the organisation gets
sector_key = NULL.

Revision ID: e71c5a09d3b8
Revises: 4b8e2d61c0aa
Create Date: 2026-10-22 18:00:00.000000

"""
import logging
import uuid
from collections import Counter, defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# The normaliser is a small pure function shared with the app (the brief asks to
# reuse it); a later change to its aliases won't re-run this data migration.
from app.domain.governance import normalize_sector

# revision identifiers, used by Alembic.
revision: str = 'e71c5a09d3b8'
down_revision: Union[str, Sequence[str], None] = '4b8e2d61c0aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    rows = conn.execute(sa.text(
        "SELECT id, tenant_name, sector, created_at FROM evaluations "
        "WHERE organisation_id IS NULL ORDER BY created_at DESC"
    )).all()

    by_name = defaultdict(list)
    for r in rows:
        name = (r.tenant_name or "").strip()
        if name:
            by_name[name].append(r)

    subject_types = conn.execute(sa.text("SELECT code FROM subject_types")).scalars().all()
    unmapped = Counter()

    for name, evals in by_name.items():
        # Most recent evaluation's sector that normalises wins; otherwise unmapped.
        sector_key, sub_type = None, None
        for r in evals:
            key, sub = normalize_sector(r.sector)
            if key:
                sector_key, sub_type = key, sub
                break
        if sector_key is None:
            for r in evals:
                unmapped[(r.sector or "").strip() or "<empty>"] += 1

        org_id = conn.execute(
            sa.text("SELECT id FROM organisations WHERE lower(name) = lower(:name) ORDER BY created_at LIMIT 1"),
            {"name": name},
        ).scalar()
        if org_id is None:
            org_id = uuid.uuid4()
            conn.execute(
                sa.text(
                    "INSERT INTO organisations (id, name, sector_key, sector_sub_type, country, profile_status, "
                    "profile_version) VALUES (:id, :name, :sector_key, :sub_type, 'NG', 'draft', 1)"
                ),
                {"id": org_id, "name": name, "sector_key": sector_key, "sub_type": sub_type},
            )
            if sector_key:
                codes = conn.execute(
                    sa.text(
                        "SELECT code FROM sector_code_defaults WHERE sector = :s AND sub_type IS NOT DISTINCT FROM :t"
                    ),
                    {"s": sector_key, "t": sub_type},
                ).scalars().all()
                for code in codes:
                    conn.execute(
                        sa.text(
                            "INSERT INTO organisation_governance_codes (organisation_id, code, source) "
                            "VALUES (:o, :c, 'sector_default') ON CONFLICT DO NOTHING"
                        ),
                        {"o": org_id, "c": code},
                    )

        for r in evals:
            conn.execute(sa.text("UPDATE evaluations SET organisation_id = :o WHERE id = :e"), {"o": org_id, "e": r.id})

    # Every evaluation gets all subject types in scope (the default) if it has none yet.
    for (eval_id,) in conn.execute(sa.text(
        "SELECT e.id FROM evaluations e WHERE NOT EXISTS "
        "(SELECT 1 FROM evaluation_scope_subject_types s WHERE s.evaluation_id = e.id)"
    )).all():
        for code in subject_types:
            conn.execute(
                sa.text("INSERT INTO evaluation_scope_subject_types (evaluation_id, subject_type_code) VALUES (:e, :c)"),
                {"e": eval_id, "c": code},
            )

    log.info("backfill_organisations: %d organisation(s) for %d evaluation(s)", len(by_name), len(rows))
    for sector, n in sorted(unmapped.items()):
        log.warning("backfill_organisations: sector %r did not map to a sector key (%d evaluation(s))", sector, n)


def downgrade() -> None:
    """Downgrade schema."""
    # Data stays valid at the previous revision; the schema migration's downgrade drops the tables.
    pass
