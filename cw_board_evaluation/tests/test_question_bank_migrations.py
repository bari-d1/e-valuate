"""
Migration test for the question bank revision, on a throwaway database
("<test database>_question_bank_migrations").

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL with CREATEDB rights.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
BEFORE = "c47e9d13a6b2"  # last director profile revision
NEW_TABLES = {"question_bank_items", "question_bank_item_subject_types", "question_bank_item_clauses"}


@pytest.fixture
def migration_db(monkeypatch):
    if os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")
    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_question_bank_migrations")
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except Exception as exc:  # pragma: no cover - environment dependent
        admin.dispose()
        pytest.skip(f"Cannot create migration test database: {exc}")
    url_str = url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url_str)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    engine = create_engine(url_str)
    try:
        yield cfg, engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        admin.dispose()


def _tables(engine) -> set:
    with engine.connect() as conn:
        return set(conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )).scalars())


def test_upgrade_downgrade_upgrade(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)

    item_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO question_bank_items (id, code, version, status, text, answer_type, theme_code, "
            "evidence_source_code, subject_binding, known_from_behaviour, placeholders, source_refs, tag_notes, "
            "weight, sort_order) VALUES (:id, 'BOARD-EFF-01', 1, 'draft', 'Text', 'yesno', 'GENERAL', 'PERCEPTION', "
            "'none', 'skip', '[]', '[]', '{}', 1, 0)"), {"id": item_id})
        conn.execute(text("INSERT INTO question_bank_item_subject_types VALUES (:id, 'BOARD')"), {"id": item_id})
        # (code, version) is unique
        with pytest.raises(Exception):
            with conn.begin_nested():
                conn.execute(text(
                    "INSERT INTO question_bank_items (id, code, version, status, text, answer_type, theme_code, "
                    "evidence_source_code, subject_binding, known_from_behaviour, placeholders, source_refs, tag_notes, "
                    "weight, sort_order) VALUES (:id, 'BOARD-EFF-01', 1, 'draft', 'Text', 'yesno', 'GENERAL', "
                    "'PERCEPTION', 'none', 'skip', '[]', '[]', '{}', 1, 0)"), {"id": uuid.uuid4()})

    command.downgrade(cfg, BEFORE)
    assert not (NEW_TABLES & _tables(engine))
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)
