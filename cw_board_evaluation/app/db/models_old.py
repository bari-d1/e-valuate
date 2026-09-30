"""
app.db.models
-------------
SQLAlchemy models for the C&W Board Evaluation platform (MVP).

Includes:
- Evaluation: one evaluation cycle (client + year + sector)
- Report: AI-generated report persisted as JSON
- Participant: invited board evaluator(s)
- Question: the questionnaire/instrument definition (versionable)
- Response: answers submitted by participants to questions

Note:
- For MVP we use create_all() elsewhere to create new tables.
- For production, use Alembic migrations (create_all won't alter existing columns).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Column, Integer, String

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)



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


    instrument_template_code = Column(String, nullable=False, default="DEFAULT")
    instrument_version = Column(Integer, nullable=False, default=1)

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

    __table_args__ = (
        Index("ix_evaluations_tenant_year", "tenant_name", "year"),
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
# Participants / Questions / Responses
# ----------------------------

class Participant(Base):
    """
    An invited evaluator (director / board member / company secretary).
    """

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    access_token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
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

    __table_args__ = (
        Index("ix_participants_evaluation", "evaluation_id"),
        Index("ix_participants_email", "email"),
        Index("ix_participants_access_token", "access_token"),
        UniqueConstraint("evaluation_id", "email", name="uq_participant_eval_email"),
        UniqueConstraint("access_token", name="uq_participant_access_token"),
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    responses: Mapped[list["Response"]] = relationship(back_populates="question")

    __table_args__ = (
        Index("ix_questions_template_version", "template_code", "version"),
        Index("ix_questions_dimension", "dimension"),
        UniqueConstraint("template_code", "version", "text", name="uq_question_template_version_text"),
    )


class Response(Base):
    """
    One participant's answer to one question.

    For rating questions:
    - score: 1..5 (or 1..10 later)
    For comment questions:
    - comment contains the text
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

    __table_args__ = (
        UniqueConstraint("participant_id", "question_id", name="uq_response_participant_question"),
        Index("ix_responses_evaluation", "evaluation_id"),
        Index("ix_responses_question", "question_id"),
        Index("ix_responses_participant", "participant_id"),
    )
