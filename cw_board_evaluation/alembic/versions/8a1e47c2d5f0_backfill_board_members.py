"""backfill_board_members

Data migration: one board member per person per organisation, built from the
participants of evaluations that have an organisation. People are matched on
lower(trim(email)) within the organisation, so someone who took part in several
evaluations becomes one board member. Participants are linked to it.

Where Participant.role maps to a governance role, a PROPOSED governance_role
fact is created (source "consultant": it came from the evaluation roster), for
a consultant to confirm. The most recent evaluation's role wins; differing
roles from other evaluations are listed in the fact's note.

Logged: participants whose role didn't map, and evaluations with no
organisation (their participants are not linked).

Idempotent: participants already linked are skipped and existing board members
are reused. Downgrade leaves the data (the schema migration drops the tables).

Revision ID: 8a1e47c2d5f0
Revises: 6d2f0b8a91c4
Create Date: 2026-10-27 10:00:00.000000

"""
import json
import logging
import uuid
from collections import OrderedDict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Small pure function shared with the app (as in backfill_organisations)
from app.domain.board_member_profile import governance_role_from_participant_role

# revision identifiers, used by Alembic.
revision: str = '8a1e47c2d5f0'
down_revision: Union[str, Sequence[str], None] = '6d2f0b8a91c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    no_org = conn.execute(sa.text(
        "SELECT e.id, count(p.id) AS n FROM evaluations e LEFT JOIN participants p ON p.evaluation_id = e.id "
        "WHERE e.organisation_id IS NULL GROUP BY e.id ORDER BY e.id"
    )).all()

    rows = conn.execute(sa.text(
        "SELECT p.id, p.email, p.full_name, p.role, e.id AS evaluation_id, e.organisation_id, e.created_at "
        "FROM participants p JOIN evaluations e ON e.id = p.evaluation_id "
        "WHERE e.organisation_id IS NOT NULL AND p.board_member_id IS NULL "
        "ORDER BY e.created_at DESC, p.created_at"
    )).all()

    # (organisation_id, email) -> participants, most recent evaluation first
    people = OrderedDict()
    for r in rows:
        email = (r.email or "").strip().lower()
        if email:
            people.setdefault((r.organisation_id, email), []).append(r)

    created = linked = proposed = 0
    unmapped = []
    for (org_id, email), parts in people.items():
        member_id = conn.execute(
            sa.text("SELECT id FROM board_members WHERE organisation_id = :o AND lower(email) = :e"),
            {"o": org_id, "e": email},
        ).scalar()
        if member_id is None:
            member_id = uuid.uuid4()
            name = next(((p.full_name or "").strip() for p in parts if (p.full_name or "").strip()), email)
            conn.execute(sa.text(
                "INSERT INTO board_members (id, organisation_id, full_name, email, active, profile_status, profile_version) "
                "VALUES (:id, :o, :n, :e, true, 'draft', 1)"
            ), {"id": member_id, "o": org_id, "n": name, "e": email})
            created += 1

        for p in parts:
            conn.execute(sa.text("UPDATE participants SET board_member_id = :m WHERE id = :p"), {"m": member_id, "p": p.id})
            linked += 1

        roles = []  # (governance_role, evaluation_id), most recent first
        for p in parts:
            g = governance_role_from_participant_role(p.role)
            if g:
                roles.append((g, p.evaluation_id))
            else:
                unmapped.append((p.evaluation_id, email, p.role))
        if not roles:
            continue
        has_fact = conn.execute(sa.text(
            "SELECT 1 FROM board_member_facts WHERE board_member_id = :m AND key = 'governance_role' "
            "AND status IN ('proposed', 'confirmed')"
        ), {"m": member_id}).first()
        if has_fact:
            continue
        role, from_eval = roles[0]
        others = sorted({f"{g} ({e})" for g, e in roles[1:] if g != role})
        note = f"From the participant role in evaluation {from_eval}."
        if others:
            note += " Other evaluations gave: " + ", ".join(others) + "."
        conn.execute(sa.text(
            "INSERT INTO board_member_facts (id, board_member_id, key, value, source, status, origin, note) "
            "VALUES (:id, :m, 'governance_role', CAST(:v AS jsonb), 'consultant', 'proposed', 'manual', :note)"
        ), {"id": uuid.uuid4(), "m": member_id, "v": json.dumps(role), "note": note})
        proposed += 1

    log.info(
        "backfill_board_members: %d board member(s) created, %d participant(s) linked, %d governance_role proposal(s)",
        created, linked, proposed,
    )
    for eval_id, email, role in unmapped:
        log.warning("backfill_board_members: role %r for %s in %s did not map to a governance role", role, email, eval_id)
    for r in no_org:
        log.warning("backfill_board_members: evaluation %s has no organisation; %d participant(s) not linked", r.id, r.n)


def downgrade() -> None:
    """Downgrade schema."""
    # Data stays valid at the previous revision; the schema migration's downgrade drops the tables.
    pass
