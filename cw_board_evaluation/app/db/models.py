"""
app.db.models
-------------
SQLAlchemy models for the C&W Board Evaluation platform (MVP).

Includes:
- Evaluation: one evaluation cycle (client + year + sector)
- Report: AI-generated report persisted as JSON
- Participant: invited board evaluator(s)
- AssessmentAssignment: granular assessment tasks with per-assignment token (NEW)
- Question: the questionnaire/instrument definition (versionable)
- Response: answers submitted by participants to questions

Note:
- For MVP we use create_all() elsewhere to create new tables.
- For production, use Alembic migrations (create_all won't alter existing columns).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import text as sql_text  # Question has a column named "text"
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ----------------------------
# Core: Evaluations + Reports
# ----------------------------

class Evaluation(Base):
    """One board evaluation cycle for a client (e.g., Demo Client Plc, 2025)."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # e.g. "eval-001"
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Keep instrument selection on evaluation (used as default for assignments)
    instrument_template_code: Mapped[str] = mapped_column(String(64), nullable=False, default="DEFAULT")
    instrument_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # JSON like {"items": ["NAICOM","FRC"]}
    regulators: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Company context. tenant_name / sector / regulators above are kept in sync
    # from the organisation (app.services.organisations.sync_evaluation_from_organisation)
    # because reports, exports, the portal and emails still read them.
    organisation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    review_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    review_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    brief: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # "draft" | "in_review" | "live" | "closed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")
    # Methodology options (app.domain.evaluation_options), e.g. {"peer_mode": "full"}; missing keys use defaults
    options: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, default=dict, server_default="{}"
    )
    # Shown at the start of the participant's form and in their invite email. NULL uses neutral
    # default wording (app.services.participant_portal.default_notice) that promises nothing about anonymity.
    participant_notice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Automatic reminders (app.services.reminders.DEFAULT_SETTINGS); missing keys use the defaults, off until switched on
    reminder_settings: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, default=dict, server_default="{}"
    )

    # Relationships
    reports: Mapped[list["Report"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )
    responses: Mapped[list["Response"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )

    # ✅ NEW: granular assignments (per-assignment tokens)
    assignments: Mapped[list["AssessmentAssignment"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )

    # ✅ NEW: track configs enabled for this evaluation (multi-track engine)
    tracks: Mapped[list["EvaluationTrack"]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
    )


    __table_args__ = (
        Index("ix_evaluations_tenant_year", "tenant_name", "year"),
        Index("ix_evaluations_organisation", "organisation_id"),
        CheckConstraint(
            "status IN ('draft', 'in_review', 'live', 'closed')",
            name="ck_evaluations_status",
        ),
    )


class AssessmentTrackTemplate(Base):
    """
    A reusable "track definition" (global library).

    Examples:
    - BOARD_AS_WHOLE
    - CHAIR_EVAL (INED-only raters)
    - DIRECTOR_SELF
    - DIRECTOR_PEER
    - COMMITTEE_EVAL
    - GOV_AUDIT

    These templates get enabled per evaluation via EvaluationTrack.
    """

    __tablename__ = "assessment_track_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # e.g. "CHAIR_EVAL"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Maps to AssessmentAssignment.assignment_type
    assignment_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Subject behavior:
    # "NONE" | "PARTICIPANT_ROLE" | "PARTICIPANT_SELF" | "PARTICIPANT_EACH" | "COMMITTEE"
    subject_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="NONE")
    subject_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Stored as JSON for flexibility:
    # {"mode":"ALL"} or {"mode":"ROLE_IN","roles":["INED"]}
    respondent_rule: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False,
    )

    # Default instrument for this track (overridable per evaluation)
    default_template_code: Mapped[str] = mapped_column(String(64), nullable=False, default="DEFAULT")
    default_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    evaluation_tracks: Mapped[list["EvaluationTrack"]] = relationship(
        back_populates="track_template",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_track_templates_code", "code"),
        Index("ix_track_templates_active", "active"),
    )


class EvaluationTrack(Base):
    """
    Per-evaluation configuration: which track templates are enabled for an evaluation,
    plus optional per-evaluation overrides (instrument + config).

    This is what the consultant UX will manage.
    """

    __tablename__ = "evaluation_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )

    track_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_track_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )

    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Optional per-evaluation instrument override (if null, use template default -> else evaluation default)
    instrument_template_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    instrument_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Track-specific config (committees list, inclusion rules, etc.)
    config: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    evaluation: Mapped["Evaluation"] = relationship(back_populates="tracks")
    track_template: Mapped["AssessmentTrackTemplate"] = relationship(back_populates="evaluation_tracks")

    __table_args__ = (
        UniqueConstraint("evaluation_id", "track_template_id", name="uq_eval_track"),
        Index("ix_eval_tracks_eval", "evaluation_id"),
        Index("ix_eval_tracks_tpl", "track_template_id"),
        Index("ix_eval_tracks_enabled", "enabled"),
    )

class Report(Base):
    """
    AI-generated report saved as structured JSON (institutional memory).

    IMPORTANT:
    If your Postgres schema has:
      reports.id = character varying(64)

    then this model MUST use String(64) for id (not UUID),
    otherwise SQLAlchemy may query WHERE id = $1::UUID and Postgres will fail.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # store str(uuid.uuid4()) in code
    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    summary_json: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    evaluation: Mapped["Evaluation"] = relationship(back_populates="reports")

    __table_args__ = (
        Index("ix_reports_evaluation_created_at", "evaluation_id", "created_at"),
    )


# ----------------------------
# Taxonomy lookup tables (see app.domain.taxonomy)
# ----------------------------

class SubjectType(Base):
    """WHO or WHAT is being evaluated (e.g. BOARD, CHAIR, INED, COMMITTEE)."""

    __tablename__ = "subject_types"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "single" | "per_person" | "per_committee"
    cardinality: Mapped[str] = mapped_column(String(16), nullable=False)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint(
            "cardinality IN ('single', 'per_person', 'per_committee')",
            name="ck_subject_types_cardinality",
        ),
    )


class Theme(Base):
    """WHICH ASPECT is being evaluated. Provisional list: names are data, not code."""

    __tablename__ = "themes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EvidenceSource(Base):
    """WHAT KIND of evidence a question gathers (PERCEPTION, ROLE_SELF, ORG_FACT)."""

    __tablename__ = "evidence_sources"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ----------------------------
# Participants / Assignments / Questions / Responses
# ----------------------------

class Participant(Base):
    """
    An invited evaluator (director / board member / company secretary).

    Token model (Phase 4):
    - Participant.access_token is the **hub token** (personal task hub: /member/hub/{token}).
      API field name: hub_token (access_token column retained for DB compatibility).
    - Per-questionnaire tokens live on AssessmentAssignment.access_token (assignment_token in API).

    Important:
    - access_token is nullable to avoid unique-constraint collisions on default "".
      (Postgres treats "" as a real value, so multiple rows would violate uniqueness.)
    """

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ✅ FIX: nullable token (avoid duplicate "" clashes with unique constraint)
    access_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default=None)
    token_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Examples: "Chair", "INED", "ED", "Company Secretary"
    role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # The organisation-level person this participant is (profiles carry over year to year)
    board_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_members.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String(32), default="invited", nullable=False)

    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    evaluation: Mapped["Evaluation"] = relationship(back_populates="participants")
    responses: Mapped[list["Response"]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )

    # ✅ NEW: assignments where this participant is the respondent (the one who fills the form)
    assignments_as_respondent: Mapped[list["AssessmentAssignment"]] = relationship(
        back_populates="respondent",
        foreign_keys=lambda: [AssessmentAssignment.respondent_participant_id],
        cascade="all, delete-orphan",
    )

    # ✅ NEW: assignments where this participant is the subject (the person/thing being evaluated)
    assignments_as_subject: Mapped[list["AssessmentAssignment"]] = relationship(
        back_populates="subject",
        foreign_keys=lambda: [AssessmentAssignment.subject_participant_id],
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_participants_evaluation", "evaluation_id"),
        Index("ix_participants_email", "email"),
        Index("ix_participants_access_token", "access_token"),
        UniqueConstraint("evaluation_id", "email", name="uq_participant_eval_email"),
        UniqueConstraint("access_token", name="uq_participant_access_token"),
    )


class AssessmentAssignment(Base):
    """
    A granular assessment task within an evaluation, with its own assignment token.

    AssessmentAssignment.access_token is exposed as assignment_token in consultant APIs.
    It opens a single questionnaire (/member/{token}/questions), not the participant hub.

    Why this exists:
    - Your real-world process requires multiple distinct assessments per evaluation:
      board-as-a-whole, self assessments, peer reviews, chair evaluations, committee evaluations,
      CEO evaluations, ED evaluations, governance audit, etc.
    - Each *assignment* should have its own token and status so we can track completion accurately.

    Minimal-change design:
    - We do NOT remove Participant or Response. We add this table first.
    - Next step (later): link responses to assignment (either by adding assignment_id to responses,
      or introducing an assignment_responses table).
    """

    __tablename__ = "assessment_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Who fills the assessment
    respondent_participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Who/what is being evaluated (nullable for things like "Board as a whole", "Committee", "Governance Audit")
    subject_participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
    )

    # e.g.:
    # "BOARD_AS_WHOLE" | "DIRECTOR_SELF" | "DIRECTOR_PEER" | "CHAIR_EVAL" | "COMMITTEE_EVAL"
    # "CEO_SELF" | "CEO_EVAL" | "ED_SELF" | "ED_EVAL" | "GOV_AUDIT"
    # "ASSEMBLED": the participant's one form for their approved question set (question_set_id)
    assignment_type: Mapped[str] = mapped_column(String(64), nullable=False, default="BOARD_AS_WHOLE")

    # Optional detail fields (useful for reporting + UX)
    committee_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Each assignment can point to an instrument (defaults to evaluation’s instrument)
    instrument_template_code: Mapped[str] = mapped_column(String(64), nullable=False, default="DEFAULT")
    instrument_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ✅ FIX: nullable token (avoid duplicate "" clashes with unique constraint)
    access_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default=None)
    token_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="invited", nullable=False)

    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ASSEMBLED assignments: the question set behind the form, and when the participant
    # first opened it, last saved an answer, submitted, and when their link was last emailed
    question_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participant_question_sets.id", ondelete="SET NULL"), nullable=True
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    evaluation: Mapped["Evaluation"] = relationship(back_populates="assignments")

    respondent: Mapped["Participant"] = relationship(
        back_populates="assignments_as_respondent",
        foreign_keys=lambda: [AssessmentAssignment.respondent_participant_id],
    )

    subject: Mapped[Optional["Participant"]] = relationship(
        back_populates="assignments_as_subject",
        foreign_keys=lambda: [AssessmentAssignment.subject_participant_id],
    )

    __table_args__ = (
        Index("ix_assignments_evaluation", "evaluation_id"),
        Index("ix_assignments_respondent", "respondent_participant_id"),
        Index("ix_assignments_subject", "subject_participant_id"),
        Index("ix_assignments_token", "access_token"),
        # One form per participant for assembled evaluations (the dedup constraint below treats NULLs as distinct)
        Index("uq_assignment_one_assembled", "respondent_participant_id", unique=True,
              postgresql_where=sql_text("assignment_type = 'ASSEMBLED'")),
        UniqueConstraint("access_token", name="uq_assignment_access_token"),
        # Prevent accidental duplicates for common cases:
        # same respondent doing same type for same subject/committee within same evaluation
        UniqueConstraint(
            "evaluation_id",
            "respondent_participant_id",
            "assignment_type",
            "subject_participant_id",
            "committee_name",
            name="uq_assignment_dedup",
        ),
    )


class Question(Base):
    """
    A question in the board evaluation instrument.

    For versioning/template control:
    - template_code groups a set of questions (e.g., "INSURANCE_V1")
    - version increments when the instrument changes
    """

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    template_code: Mapped[str] = mapped_column(String(64), default="DEFAULT", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # e.g. "Risk Oversight", "Board Composition"
    dimension: Mapped[str] = mapped_column(String(120), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # "rating" | "yesno" | "comment"
    answer_type: Mapped[str] = mapped_column(String(32), default="rating", nullable=False)

    # weighting supports dimension scoring
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # SQLite-friendly bool; for Postgres this is fine too
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Taxonomy tags (optional). `dimension` above is unchanged and still drives
    # analytics, portal ordering and exports.
    theme_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("themes.code", ondelete="RESTRICT"),
        nullable=True,
    )
    evidence_source_code: Mapped[Optional[str]] = mapped_column(
        String(32),
        ForeignKey("evidence_sources.code", ondelete="RESTRICT"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ---- Assembled questions (one participant's tailored set). All NULL on
    # legacy template questions, which behave exactly as before. Assembled
    # rows use template_code "P:<participant id>" so template queries never see them.
    evaluation_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=True
    )
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )
    bank_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_bank_items.id", ondelete="SET NULL"), nullable=True
    )
    bank_item_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The subject instance the question is about (the board, a committee, a person)
    evaluation_subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_subjects.id", ondelete="SET NULL"), nullable=True
    )
    # "board" | "committees" | "colleagues" | "yourself" | "confirm" | "additional"
    section: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # "draft" | "approved" | "locked" (follows the participant's set), or "removed" by a consultant:
    # kept for audit, left out of the participant's form, counts and coverage
    status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    removed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The rule reasons selection included the question for ("Included: respondent is ...")
    selection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Who added the question by hand (from the bank or written); NULL when assembly added it
    added_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bank_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # bank wording after placeholders
    ai_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI suggestion, never used until chosen
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Which wording `text` holds: "bank" | "ai_tailored" | "ai_new" | "consultant_edited" | "consultant_written"
    text_source: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    # AI new-question suggestions: "pending" | "accepted" | "rejected", and the fact they respond to
    suggestion_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ai_fact_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # "If so..." follow-ups: shown only when the parent's answer matches show_if, e.g. {"answer": "yes"}
    depends_on_question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    show_if: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    # known_from "confirm" items: the stored value the participant is asked to confirm
    confirm_value: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    options: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    scale: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    responses: Mapped[list["Response"]] = relationship(back_populates="question")

    # Subject TYPES this question is about (e.g. COMMITTEE). Which committee or
    # director a response is about is decided at assembly time, not here.
    subject_type_links: Mapped[list["QuestionSubjectType"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="QuestionSubjectType.subject_type_code",
    )

    @property
    def subject_type_codes(self) -> list[str]:
        return [link.subject_type_code for link in self.subject_type_links]

    __table_args__ = (
        Index("ix_questions_template_version", "template_code", "version"),
        Index("ix_questions_dimension", "dimension"),
        Index("ix_questions_theme", "theme_code"),
        Index("ix_questions_evidence_source", "evidence_source_code"),
        # Unique text per template for legacy questions only: two participants (or one participant
        # rating several colleagues) legitimately get identical assembled text.
        Index(
            "uq_question_template_version_text", "template_code", "version", "text",
            unique=True, postgresql_where=sql_text("participant_id IS NULL"),
        ),
        Index("ix_questions_participant", "participant_id"),
        Index("ix_questions_evaluation", "evaluation_id"),
        CheckConstraint(
            "section IS NULL OR section IN ('board', 'committees', 'colleagues', 'yourself', 'confirm', 'additional')",
            name="ck_questions_section",
        ),
        CheckConstraint("status IS NULL OR status IN ('draft', 'approved', 'locked', 'removed')",
                        name="ck_questions_status"),
        CheckConstraint(
            "text_source IS NULL OR text_source IN ('bank', 'ai_tailored', 'ai_new', 'consultant_edited', "
            "'consultant_written')",
            name="ck_questions_text_source",
        ),
    )


class QuestionSubjectType(Base):
    """Join table: which subject types a question relates to (many-to-many)."""

    __tablename__ = "question_subject_types"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subject_type_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("subject_types.code", ondelete="RESTRICT"),
        primary_key=True,
    )

    question: Mapped["Question"] = relationship(back_populates="subject_type_links")

    __table_args__ = (
        Index("ix_question_subject_types_subject_type", "subject_type_code"),
    )


class EvaluationSubject(Base):
    """
    A concrete subject within one evaluation: the board, a committee, or a
    person in a role (e.g. "INED: Jane Doe"). Built from existing evaluation
    data by app.services.evaluation_subjects.sync_evaluation_subjects.

    Shape by cardinality of the subject type:
      single        -> participant_id NULL (BOARD) or the one person (CHAIR, MD_CEO, COMPANY_SECRETARY)
      per_person    -> participant_id set (ED, NED, INED)
      per_committee -> committee_name set (COMMITTEE)
    """

    __tablename__ = "evaluation_subjects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_type_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("subject_types.code", ondelete="RESTRICT"),
        nullable=False,
    )
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=True,
    )
    committee_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    label: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # NULLS NOT DISTINCT so e.g. a second BOARD row (both NULLs) is rejected too.
        UniqueConstraint(
            "evaluation_id",
            "subject_type_code",
            "participant_id",
            "committee_name",
            name="uq_evaluation_subject",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "participant_id IS NULL OR committee_name IS NULL",
            name="ck_evaluation_subjects_one_target",
        ),
        Index("ix_evaluation_subjects_evaluation", "evaluation_id"),
        Index("ix_evaluation_subjects_participant", "participant_id"),
    )


class Response(Base):
    """
    One participant's answer to one question.

    For rating questions:
    - score: 1..5 (or 1..10 later)
    For comment questions:
    - comment contains the text

    NOTE:
    - For minimal changes, this still links to participant + evaluation + question.
    - Next step (later): associate responses to AssessmentAssignment (assignment_id)
      so the same participant can submit multiple distinct assessments cleanly.
    """

    __tablename__ = "responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)



    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id", ondelete="CASCADE"),
        nullable=False,
    )

    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_assignments.id", ondelete="CASCADE"),
        nullable=True,
    )

    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Assembled forms: the full answer (e.g. {"value": "yes"}, {"values": [...]}, {"dont_know": true},
    # {"confirm": "needs_updating", "correction": "..."}) and the subject it's about, copied from the question.
    # score still holds ratings (and 1/0 for yes/no) so existing analytics keep working.
    answer: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    evaluation_subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_subjects.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="responses")
    participant: Mapped["Participant"] = relationship(back_populates="responses")
    question: Mapped["Question"] = relationship(back_populates="responses")
    assignment: Mapped[Optional["AssessmentAssignment"]] = relationship()







    __table_args__ = (
        UniqueConstraint("assignment_id", "question_id", name="uq_response_assignment_question"),
        Index("ix_responses_assignment", "assignment_id"),
        Index("ix_responses_evaluation", "evaluation_id"),
        Index("ix_responses_question", "question_id"),
        Index("ix_responses_participant", "participant_id"),
    )


# ----------------------------
# Governance code library
# ----------------------------

class GovernanceCode(Base):
    """
    One edition of a corporate governance code (e.g. NCCG_2018). A new edition
    is a new row with a new code, never an overwrite, so evaluations can record
    exactly which version they used.
    """

    __tablename__ = "governance_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "NCCG_2018"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False, default="NG")

    # NULL = cross-sector (e.g. NCCG)
    sector: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    version: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # "current" | "historical" | "superseded"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="current")

    # Sector guidelines that are read together with a base code (e.g. NAICOM -> NCCG)
    supplements_code: Mapped[Optional[str]] = mapped_column(
        String(32),
        ForeignKey("governance_codes.code", ondelete="RESTRICT"),
        nullable=True,
    )

    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    clauses_loaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('current', 'historical', 'superseded')",
            name="ck_governance_codes_status",
        ),
    )


class GovernanceClause(Base):
    """
    A numbered clause of a governance code, as printed (e.g. NCCG "2.7",
    "11.1.6"; NAICOM "2.01"). Hierarchy via parent_id:
      NCCG:   part > principle > practice (> practice)
      NAICOM: section > subsection
    """

    __tablename__ = "governance_clauses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("governance_codes.code", ondelete="CASCADE"),
        nullable=False,
    )
    reference: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("governance_clauses.id", ondelete="CASCADE"),
        nullable=True,
    )

    # "part" | "principle" | "practice" | "section" | "subsection"
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    heading: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # A clause in another code this one builds on ("In addition to Principle 2.7 of the NCCG 2018")
    cites_clause_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("governance_clauses.id", ondelete="SET NULL"),
        nullable=True,
    )

    theme_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("themes.code", ondelete="RESTRICT"),
        nullable=True,
    )

    subject_type_links: Mapped[list["GovernanceClauseSubjectType"]] = relationship(
        back_populates="clause",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="GovernanceClauseSubjectType.subject_type_code",
    )

    @property
    def subject_type_codes(self) -> list[str]:
        return [link.subject_type_code for link in self.subject_type_links]

    __table_args__ = (
        UniqueConstraint("code", "reference", name="uq_governance_clause_code_reference"),
        CheckConstraint(
            "level IN ('part', 'principle', 'practice', 'section', 'subsection')",
            name="ck_governance_clauses_level",
        ),
        Index("ix_governance_clauses_code_sort", "code", "sort_order"),
        Index("ix_governance_clauses_parent", "parent_id"),
        Index("ix_governance_clauses_theme", "theme_code"),
    )


class GovernanceClauseSubjectType(Base):
    """Join table: which subject types a governance clause applies to."""

    __tablename__ = "governance_clause_subject_types"

    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("governance_clauses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    subject_type_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("subject_types.code", ondelete="RESTRICT"),
        primary_key=True,
    )

    clause: Mapped["GovernanceClause"] = relationship(back_populates="subject_type_links")

    __table_args__ = (
        Index("ix_governance_clause_subject_types_subject_type", "subject_type_code"),
    )


class SectorCodeDefault(Base):
    """Which governance codes apply by default to a sector (optionally a sub-type)."""

    __tablename__ = "sector_code_defaults"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sector: Mapped[str] = mapped_column(String(64), nullable=False)  # normalised key, e.g. "insurance"
    sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # e.g. "microfinance"
    code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("governance_codes.code", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "sector", "sub_type", "code",
            name="uq_sector_code_default",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_sector_code_defaults_sector", "sector"),
    )


class EvaluationGovernanceCode(Base):
    """
    The governance codes an evaluation is assessed against. Linking the
    specific code row (e.g. NCCG_2018) records which edition was used.
    """

    __tablename__ = "evaluation_governance_codes"

    evaluation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("governance_codes.code", ondelete="RESTRICT"),
        primary_key=True,
    )

    # "sector_default" | "manual"
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('sector_default', 'manual')",
            name="ck_evaluation_governance_codes_source",
        ),
    )


# ----------------------------
# Company context: organisations, documents, profile facts, committees
# ----------------------------

class Organisation(Base):
    """
    A client company, created once and reused by every year's evaluation.
    Its profile (facts + committees) is proposed (manually or by AI) and
    confirmed by a consultant; marking it reviewed bumps profile_version.
    """

    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Sector keys from app.domain.governance (e.g. "insurance"); NULL when not known
    sector_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sector_sub_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # e.g. "microfinance"
    country: Mapped[str] = mapped_column(String(8), nullable=False, default="NG")

    # "draft" | "reviewed"
    profile_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("profile_status IN ('draft', 'reviewed')", name="ck_organisations_profile_status"),
        Index("ix_organisations_name", "name"),
    )


class OrgDocument(Base):
    """A document uploaded for an organisation. The file lives in storage under storage_key."""

    __tablename__ = "org_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    # company_profile | board_structure | committee_tor | governance_policy | annual_report | public_info | other
    # | director_profile (board_member_id set)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Set for a board member's own documents (doc_type director_profile)
    board_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("board_members.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # sanitised original name, for display
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # pending | done | failed
    extraction_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    extraction_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('company_profile', 'board_structure', 'committee_tor', 'governance_policy', "
            "'annual_report', 'public_info', 'other', 'director_profile')",
            name="ck_org_documents_doc_type",
        ),
        CheckConstraint("extraction_status IN ('pending', 'done', 'failed')", name="ck_org_documents_extraction_status"),
        UniqueConstraint("storage_key", name="uq_org_documents_storage_key"),
        Index("ix_org_documents_organisation", "organisation_id"),
        Index("ix_org_documents_board_member", "board_member_id"),
    )


class OrganisationFact(Base):
    """
    One profile fact (key from app.domain.org_profile.FACT_REGISTRY).
    Every fact records its source (public | client | consultant). AI only
    proposes; a consultant confirms. At most one confirmed and one proposed
    fact per key.
    """

    __tablename__ = "organisation_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # public | client | consultant
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")  # proposed | confirmed | rejected
    # ai_extraction | manual | participant (a correction from a participant's confirm item, always proposed)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # verbatim quote
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("source IN ('public', 'client', 'consultant')", name="ck_organisation_facts_source"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_organisation_facts_status"),
        CheckConstraint("origin IN ('ai_extraction', 'manual', 'participant')", name="ck_organisation_facts_origin"),
        Index("ix_organisation_facts_organisation", "organisation_id"),
        Index(
            "uq_organisation_facts_one_confirmed", "organisation_id", "key",
            unique=True, postgresql_where=text("status = 'confirmed'"),
        ),
        # Participant corrections sit beside any other proposal: several participants may correct the same fact
        Index(
            "uq_organisation_facts_one_proposed", "organisation_id", "key",
            unique=True, postgresql_where=text("status = 'proposed' AND origin <> 'participant'"),
        ),
    )


class OrgCommittee(Base):
    """
    A board committee as written in the client's documents (or entered by a
    consultant). Members are names for now; linking them to participants
    comes later.
    """

    __tablename__ = "org_committees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # audit | risk | remuneration | nomination | finance | governance | other
    committee_type: Mapped[str] = mapped_column(String(16), nullable=False, default="other")
    chair_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    member_names: Mapped[list] = mapped_column(MutableList.as_mutable(JSONB), nullable=False, default=list)
    terms_of_reference_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_documents.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # public | client | consultant
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")  # proposed | confirmed | rejected
    # Provenance for AI proposals (same rules as facts)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # ai_extraction | manual
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "committee_type IN ('audit', 'risk', 'remuneration', 'nomination', 'finance', 'governance', 'other')",
            name="ck_org_committees_type",
        ),
        CheckConstraint("source IN ('public', 'client', 'consultant')", name="ck_org_committees_source"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_org_committees_status"),
        CheckConstraint("origin IN ('ai_extraction', 'manual')", name="ck_org_committees_origin"),
        Index("ix_org_committees_organisation", "organisation_id"),
    )


class OrganisationGovernanceCode(Base):
    """Governance codes that apply to an organisation (sector defaults plus manual additions)."""

    __tablename__ = "organisation_governance_codes"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(
        String(32), ForeignKey("governance_codes.code", ondelete="RESTRICT"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # sector_default | manual

    __table_args__ = (
        CheckConstraint("source IN ('sector_default', 'manual')", name="ck_organisation_governance_codes_source"),
    )


class EvaluationScopeSubjectType(Base):
    """Subject types in scope for an evaluation (default: all eight)."""

    __tablename__ = "evaluation_scope_subject_types"

    evaluation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), primary_key=True
    )
    subject_type_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_types.code", ondelete="RESTRICT"), primary_key=True
    )


class EvaluationContextSnapshot(Base):
    """
    Frozen copy of the organisation context an evaluation used: confirmed
    facts, committees, documents and governance codes at that moment.
    """

    __tablename__ = "evaluation_context_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    facts: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    committees: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    document_ids: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    governance_codes: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    # Per participant: board member, profile version, confirmed facts, committee memberships
    participants: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    # generation_only facts (e.g. personality_notes) by participant id, kept apart so analysis never reads them
    generation_only: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_evaluation_context_snapshots_evaluation", "evaluation_id", "created_at"),
    )


# ----------------------------
# Board members (organisation-level people) and their profiles
# ----------------------------

class BoardMember(Base):
    """
    A person on the client's board, kept at organisation level so their profile,
    documents and committee memberships carry over from one year's evaluation to
    the next. Each evaluation's Participant links here.
    """

    __tablename__ = "board_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Pseudonymous label for dry runs, e.g. "P001"
    display_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # "draft" | "reviewed"
    profile_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    profile_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("profile_status IN ('draft', 'reviewed')", name="ck_board_members_profile_status"),
        Index("ix_board_members_organisation", "organisation_id"),
        Index(
            "uq_board_members_org_email", "organisation_id", text("lower(email)"),
            unique=True, postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_board_members_org_display_code", "organisation_id", "display_code",
            unique=True, postgresql_where=text("display_code IS NOT NULL"),
        ),
    )


class BoardMemberFact(Base):
    """
    One profile fact about a board member (key from app.domain.board_member_profile).
    Same rules as OrganisationFact: every fact has a source, AI only proposes,
    at most one confirmed and one proposed fact per key.
    """

    __tablename__ = "board_member_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    board_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("board_members.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # public | client | consultant
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")  # proposed | confirmed | rejected
    # ai_extraction | manual | participant (a correction from a participant's confirm item, always proposed)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("source IN ('public', 'client', 'consultant')", name="ck_board_member_facts_source"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_board_member_facts_status"),
        CheckConstraint("origin IN ('ai_extraction', 'manual', 'participant')", name="ck_board_member_facts_origin"),
        Index("ix_board_member_facts_member", "board_member_id"),
        Index(
            "uq_board_member_facts_one_confirmed", "board_member_id", "key",
            unique=True, postgresql_where=text("status = 'confirmed'"),
        ),
        Index(
            "uq_board_member_facts_one_proposed", "board_member_id", "key",
            unique=True, postgresql_where=text("status = 'proposed' AND origin <> 'participant'"),
        ),
    )


class CommitteeMembership(Base):
    """A board member's seat on an organisation committee (member or chair)."""

    __tablename__ = "committee_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    committee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_committees.id", ondelete="CASCADE"), nullable=False
    )
    board_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("board_members.id", ondelete="CASCADE"), nullable=False
    )
    membership_role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")  # member | chair
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # public | client | consultant
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")  # proposed | confirmed | rejected
    # name_match (proposed by matching committee names) | manual
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    matched_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # the name as written on the committee
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("membership_role IN ('member', 'chair')", name="ck_committee_memberships_role"),
        CheckConstraint("source IN ('public', 'client', 'consultant')", name="ck_committee_memberships_source"),
        CheckConstraint("status IN ('proposed', 'confirmed', 'rejected')", name="ck_committee_memberships_status"),
        CheckConstraint("origin IN ('name_match', 'manual')", name="ck_committee_memberships_origin"),
        UniqueConstraint("committee_id", "board_member_id", name="uq_committee_membership"),
        Index("ix_committee_memberships_member", "board_member_id"),
    )


# ----------------------------
# Question bank: the firm's approved methodology, held as data
# ----------------------------

class QuestionBankItem(Base):
    """
    One version of a question bank item (app.domain.question_bank). Editing an
    approved item creates a new draft version; older versions stay for audit.
    Selection uses, per code, the highest approved version (or the highest
    draft when previewing drafts), and skips a code whose highest version is
    retired.
    """

    __tablename__ = "question_bank_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. "BOARD-EFF-01"
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # "draft" | "approved" | "retired"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")

    text: Mapped[str] = mapped_column(Text, nullable=False)  # may contain {placeholders}
    # "rating" | "yesno" | "comment" | "single_select" | "multi_select"
    answer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    options: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    scale: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    theme_code: Mapped[str] = mapped_column(String(64), ForeignKey("themes.code", ondelete="RESTRICT"), nullable=False)
    evidence_source_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("evidence_sources.code", ondelete="RESTRICT"), nullable=False
    )

    # "none" | "self" | "each_subject_instance" | "respondent_committees"
    subject_binding: Mapped[str] = mapped_column(String(32), nullable=False)
    respondent_rule: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # app.domain.question_rules
    activation_rule: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)

    # A fact key whose confirmed value answers the item; "skip" it or ask to "confirm" the stored value
    known_from: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    known_from_behaviour: Mapped[str] = mapped_column(String(16), nullable=False, default="skip")
    placeholders: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)  # fact keys used in the text

    guidance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # for later AI phrasing
    source_refs: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)  # historical forms, never names
    # Per tag: {"status": "suggested" | "confirmed", "reason": "..."}
    tag_notes: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "core" | "standard" | "optional": what to keep when an assessment must be shortened
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="standard", server_default="standard")
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    subject_type_links: Mapped[list["QuestionBankItemSubjectType"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="QuestionBankItemSubjectType.subject_type_code",
    )
    clause_links: Mapped[list["QuestionBankItemClause"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def subject_type_codes(self) -> list[str]:
        return [link.subject_type_code for link in self.subject_type_links]

    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_question_bank_item_code_version"),
        CheckConstraint("status IN ('draft', 'approved', 'retired')", name="ck_question_bank_items_status"),
        CheckConstraint(
            "answer_type IN ('rating', 'yesno', 'comment', 'single_select', 'multi_select')",
            name="ck_question_bank_items_answer_type",
        ),
        CheckConstraint(
            "subject_binding IN ('none', 'self', 'each_subject_instance', 'respondent_committees')",
            name="ck_question_bank_items_subject_binding",
        ),
        CheckConstraint("known_from_behaviour IN ('skip', 'confirm')", name="ck_question_bank_items_known_from_behaviour"),
        CheckConstraint("priority IN ('core', 'standard', 'optional')", name="ck_question_bank_items_priority"),
        Index("ix_question_bank_items_code", "code"),
        Index("ix_question_bank_items_status", "status"),
    )


class QuestionBankItemSubjectType(Base):
    """Join table: which subject types a question bank item is about."""

    __tablename__ = "question_bank_item_subject_types"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_bank_items.id", ondelete="CASCADE"), primary_key=True
    )
    subject_type_code: Mapped[str] = mapped_column(
        String(32), ForeignKey("subject_types.code", ondelete="RESTRICT"), primary_key=True
    )

    item: Mapped["QuestionBankItem"] = relationship(back_populates="subject_type_links")

    __table_args__ = (Index("ix_question_bank_item_subject_types_subject_type", "subject_type_code"),)


class QuestionBankItemClause(Base):
    """A governance clause an item relates to; suggested by authoring, confirmed by a consultant."""

    __tablename__ = "question_bank_item_clauses"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_bank_items.id", ondelete="CASCADE"), primary_key=True
    )
    clause_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("governance_clauses.id", ondelete="CASCADE"), primary_key=True
    )
    # "suggested" | "confirmed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested")

    item: Mapped["QuestionBankItem"] = relationship(back_populates="clause_links")
    clause: Mapped["GovernanceClause"] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("status IN ('suggested', 'confirmed')", name="ck_question_bank_item_clauses_status"),
        Index("ix_question_bank_item_clauses_clause", "clause_id"),
    )


# ----------------------------
# Assembly: one tailored question set per participant
# ----------------------------

class AssemblyRun(Base):
    """One run of question assembly for an evaluation (runs as a background job)."""

    __tablename__ = "assembly_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    # "queued" | "running" | "done" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    participant_ids: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)  # NULL = every participant
    reset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    include_drafts: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_context_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    # Per participant: assembled / skipped (with reasons) and counts
    results: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    rater_warnings: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_assembly_runs_status"),
        Index("ix_assembly_runs_evaluation", "evaluation_id", "created_at"),
    )


class ParticipantQuestionSet(Base):
    """A participant's assembled set: draft, then approved by a consultant, then locked when they open it."""

    __tablename__ = "participant_question_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    # "draft" | "approved" | "locked"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    assembly_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assembly_runs.id", ondelete="SET NULL"), nullable=True
    )
    # Known-fact skips, blocked items, coverage gaps, dropped AI suggestions, counts and time estimate
    summary: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    estimated_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # approving despite coverage gaps
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("participant_id", name="uq_participant_question_set_participant"),
        CheckConstraint("status IN ('draft', 'approved', 'locked')", name="ck_participant_question_sets_status"),
        Index("ix_participant_question_sets_evaluation", "evaluation_id"),
    )


QUESTION_SET_ACTIONS = (
    "use_bank", "use_ai", "edit", "accept_new", "reject_new", "regenerate", "edit_tags", "remove", "restore",
    "add_from_bank", "add_written", "move", "approve", "reopen", "lock",
)


class QuestionSetEvent(Base):
    """
    The audit trail of a participant's question set: every change, who made it
    and when, with what changed in `detail` (e.g. {"before": ..., "after": ...}).
    Set-level actions (approve, reopen, lock) have no question_id. Wording
    decisions are also kept in question_suggestion_decisions for the bank
    feedback loop.
    """

    __tablename__ = "question_set_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )
    question_set_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participant_question_sets.id", ondelete="SET NULL"), nullable=True
    )
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("action IN (" + ", ".join(f"'{a}'" for a in QUESTION_SET_ACTIONS) + ")",
                        name="ck_question_set_events_action"),
        Index("ix_question_set_events_evaluation", "evaluation_id", "created_at"),
        Index("ix_question_set_events_participant", "participant_id", "created_at"),
    )


class QuestionSuggestionDecision(Base):
    """
    A consultant's decision on an assembled question's wording or an AI new-question
    suggestion. Kept for audit and the bank feedback loop even if the question is
    later re-assembled (question_id is then NULL; the bank item and texts remain).
    """

    __tablename__ = "question_suggestion_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )
    bank_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("question_bank_items.id", ondelete="SET NULL"), nullable=True
    )
    bank_item_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bank_item_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # "use_bank" | "use_ai" | "edit" | "accept_new" | "reject_new"
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    bank_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('use_bank', 'use_ai', 'edit', 'accept_new', 'reject_new')",
            name="ck_question_suggestion_decisions_decision",
        ),
        Index("ix_question_suggestion_decisions_bank_item", "bank_item_code"),
        Index("ix_question_suggestion_decisions_evaluation", "evaluation_id"),
    )


PARTICIPANT_EVENT_TYPES = (
    "invite_sent", "email_failed", "reminder_sent", "opened", "first_answer", "submitted", "link_resent",
    "link_regenerated", "deadline_extended", "form_reopened", "evaluation_closed", "evaluation_reopened",
    "reminder_settings_changed",
)


class ParticipantEvent(Base):
    """
    What happened to a participant's form, for tracking and the timeline: emails sent or failed,
    opened, first answer, submitted, and consultant actions. Evaluation-wide actions (deadline,
    close) have no participant. `detail` never holds email bodies, answers or link tokens.
    `dedupe_key` is set on automatic reminders ("<assignment id>:auto:<slot>"): its unique index
    is what stops a reminder slot being sent twice, even by two runs at once.
    """

    __tablename__ = "participant_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_id: Mapped[str] = mapped_column(String(64), ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False)
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participants.id", ondelete="CASCADE"), nullable=True
    )
    assignment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_assignments.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)  # "system" | "participant" | consultant name
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("event_type IN (" + ", ".join(f"'{t}'" for t in PARTICIPANT_EVENT_TYPES) + ")",
                        name="ck_participant_events_type"),
        Index("ix_participant_events_evaluation", "evaluation_id", "created_at"),
        Index("ix_participant_events_participant", "participant_id", "created_at"),
        UniqueConstraint("dedupe_key", name="uq_participant_events_dedupe_key"),
    )
