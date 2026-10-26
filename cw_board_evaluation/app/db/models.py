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
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
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
        UniqueConstraint("template_code", "version", "text", name="uq_question_template_version_text"),
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

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
