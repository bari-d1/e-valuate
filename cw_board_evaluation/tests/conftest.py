"""
Pytest configuration.

Unit tests run without a live database.

Integration tests (marker: integration) require PostgreSQL and:
  RUN_INTEGRATION_TESTS=1

Optional: DATABASE_URL (defaults to cw_board_eval_test on localhost).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Dummy URL so `import app.*` works in unit tests without Postgres.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cw_board_eval_test",
)

INTEGRATION_ENV = "RUN_INTEGRATION_TESTS"


def _integration_enabled() -> bool:
    return os.getenv(INTEGRATION_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _postgres_reachable(url: str) -> bool:
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def integration_engine():
    if not _integration_enabled():
        pytest.skip(f"Set {INTEGRATION_ENV}=1 to run integration tests")

    url = os.environ["DATABASE_URL"]
    if not _postgres_reachable(url):
        pytest.skip(f"PostgreSQL not reachable at DATABASE_URL ({url})")

    from app.db.models import Base

    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(integration_engine):
    """Function-scoped session rolled back after each test."""
    connection = integration_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def api_client(db_session):
    """FastAPI TestClient with get_db overridden to the test transaction."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def track_templates_seeded(db_session: Session):
    """Minimal track library for generate-assignments tests."""
    from app.db.models import AssessmentTrackTemplate

    specs = [
        {
            "code": "BOARD_AS_WHOLE",
            "name": "Board as a whole",
            "assignment_type": "BOARD_AS_WHOLE",
            "subject_mode": "NONE",
            "respondent_rule": {"mode": "ALL"},
        },
        {
            "code": "COMMITTEE_EVAL",
            "name": "Committee evaluation",
            "assignment_type": "COMMITTEE_EVAL",
            "subject_mode": "COMMITTEE",
            "respondent_rule": {"mode": "ALL"},
        },
    ]
    out = []
    for spec in specs:
        row = AssessmentTrackTemplate(
            id=uuid.uuid4(),
            description="integration test",
            subject_role=None,
            default_template_code="DEFAULT",
            default_version=1,
            active=1,
            **spec,
        )
        db_session.add(row)
        out.append(row)
    db_session.flush()
    return out
