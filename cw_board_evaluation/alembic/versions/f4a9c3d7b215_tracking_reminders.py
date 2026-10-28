"""tracking_reminders

Tracking and reminders for assembled evaluations:
- participant_events: what happened to each participant's form (emails sent or
  failed, opened, first answer, submitted) and every consultant action, for the
  status, the timeline and reminder counting. dedupe_key is unique, so an
  automatic reminder slot can only ever be recorded (and sent) once;
- evaluations.reminder_settings: the automatic reminder schedule (JSON; missing
  keys use the defaults, which leave reminders off).

Revision ID: f4a9c3d7b215
Revises: e3b7f2a94c1d
Create Date: 2026-10-29 09:40:12.118204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f4a9c3d7b215'
down_revision: Union[str, Sequence[str], None] = 'e3b7f2a94c1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENT_TYPES = (
    "invite_sent", "email_failed", "reminder_sent", "opened", "first_answer", "submitted", "link_resent",
    "link_regenerated", "deadline_extended", "form_reopened", "evaluation_closed", "evaluation_reopened",
    "reminder_settings_changed",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('evaluations', sa.Column('reminder_settings', postgresql.JSONB(astext_type=sa.Text()),
                                           server_default='{}', nullable=False))
    op.create_table('participant_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('participant_id', sa.UUID(), nullable=True),
    sa.Column('assignment_id', sa.UUID(), nullable=True),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('actor', sa.String(length=255), nullable=False),
    sa.Column('dedupe_key', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("event_type IN (" + ", ".join(f"'{t}'" for t in EVENT_TYPES) + ")",
                       name='ck_participant_events_type'),
    sa.ForeignKeyConstraint(['evaluation_id'], ['evaluations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['assignment_id'], ['assessment_assignments.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedupe_key', name='uq_participant_events_dedupe_key')
    )
    op.create_index('ix_participant_events_evaluation', 'participant_events', ['evaluation_id', 'created_at'], unique=False)
    op.create_index('ix_participant_events_participant', 'participant_events', ['participant_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_participant_events_participant', table_name='participant_events')
    op.drop_index('ix_participant_events_evaluation', table_name='participant_events')
    op.drop_table('participant_events')
    op.drop_column('evaluations', 'reminder_settings')
