"""
Migration tests for the question bank and question assembly revisions, on a
throwaway database ("<test database>_question_bank_migrations").

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


ASSEMBLY = "a7c4e19b2d58"


def test_assembly_upgrade_downgrade_keeps_legacy_questions(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, ASSEMBLY)
    assert {"assembly_runs", "participant_question_sets", "question_suggestion_decisions"} <= _tables(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, "
                          "instrument_version, regulators, status) VALUES ('M-1', 'Co', 'insurance', 2025, 'DEFAULT', 1, '{}', 'draft')"))
        pid = uuid.uuid4()
        conn.execute(text("INSERT INTO participants (id, evaluation_id, email, status) VALUES (:id, 'M-1', 'P1@example.invalid', 'invited')"),
                     {"id": pid})
        legacy = "INSERT INTO questions (id, template_code, version, dimension, text, answer_type, weight, active) " \
                 "VALUES (:id, 'DEFAULT', 1, 'Board', 'Same text', 'rating', 1, 1)"
        conn.execute(text(legacy), {"id": uuid.uuid4()})
        assembled = ("INSERT INTO questions (id, template_code, version, dimension, text, answer_type, weight, active, "
                     "evaluation_id, participant_id, section, status, text_source) VALUES (:id, :tc, 1, 'Board', "
                     "'Same text', 'rating', 1, 1, 'M-1', :p, 'colleagues', 'draft', 'bank')")
        for _ in range(2):  # identical assembled text is allowed
            conn.execute(text(assembled), {"id": uuid.uuid4(), "tc": f"P:{pid}", "p": pid})
        with pytest.raises(Exception):  # legacy text is still unique per template and version
            with conn.begin_nested():
                conn.execute(text(legacy), {"id": uuid.uuid4()})

    command.downgrade(cfg, BEFORE_ASSEMBLY)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM questions")).scalar() == 1  # assembled rows removed, legacy kept
    assert "assembly_runs" not in _tables(engine)
    command.upgrade(cfg, "head")


BEFORE_ASSEMBLY = "f3b8d2c61a07"


REVIEW = "c5d2e8a91f40"


def test_review_upgrade_downgrade(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, REVIEW)
    assert "question_set_events" in _tables(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, "
                          "instrument_version, regulators, status) VALUES ('M-2', 'Co', 'insurance', 2025, 'DEFAULT', 1, '{}', 'draft')"))
        pid = uuid.uuid4()
        conn.execute(text("INSERT INTO participants (id, evaluation_id, email, status) VALUES (:id, 'M-2', 'P2@example.invalid', 'invited')"),
                     {"id": pid})
        row = ("INSERT INTO questions (id, template_code, version, dimension, text, answer_type, weight, active, "
               "evaluation_id, participant_id, section, status, text_source) VALUES (:id, :tc, 1, 'Board', :t, 'rating', "
               "1, 1, 'M-2', :p, 'board', :s, :src)")
        for t, s, src in (("Kept", "draft", "bank"), ("Removed", "removed", "bank"), ("Written", "draft", "consultant_written")):
            conn.execute(text(row), {"id": uuid.uuid4(), "tc": f"P:{pid}", "p": pid, "t": t, "s": s, "src": src})
        conn.execute(text("INSERT INTO question_set_events (id, evaluation_id, participant_id, action, detail, created_by) "
                          "VALUES (:id, 'M-2', :p, 'remove', '{}', 'Tester')"), {"id": uuid.uuid4(), "p": pid})
        with pytest.raises(Exception):  # unknown actions are refused
            with conn.begin_nested():
                conn.execute(text("INSERT INTO question_set_events (id, evaluation_id, action, detail, created_by) "
                                  "VALUES (:id, 'M-2', 'shred', '{}', 'Tester')"), {"id": uuid.uuid4()})

    command.downgrade(cfg, ASSEMBLY)
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT text FROM questions WHERE evaluation_id = 'M-2'"))] == ["Kept"]
    assert "question_set_events" not in _tables(engine)
    command.upgrade(cfg, "head")


PORTAL = "e3b7f2a94c1d"


def test_portal_upgrade_downgrade(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, PORTAL)
    org = uuid.uuid4()
    fact = ("INSERT INTO organisation_facts (id, organisation_id, key, value, source, status, origin) "
            "VALUES (:id, :org, 'board_size', :v, 'client', 'proposed', :o)")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organisations (id, name, country, profile_status, profile_version) "
                          "VALUES (:id, 'Portal Plc', 'NG', 'draft', 1)"), {"id": org})
        # Participant corrections sit beside another proposal for the same key, and beside each other
        for v, o in (("7", "ai_extraction"), ('"Eight"', "participant"), ('"Nine"', "participant")):
            conn.execute(text(fact), {"id": uuid.uuid4(), "org": org, "v": v, "o": o})
        with pytest.raises(Exception):  # still one non-participant proposal per key
            with conn.begin_nested():
                conn.execute(text(fact), {"id": uuid.uuid4(), "org": org, "v": "5", "o": "manual"})
        conn.execute(text("UPDATE evaluations SET participant_notice = 'Notice' WHERE false"))

    command.downgrade(cfg, REVIEW)
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT origin FROM organisation_facts"))] == ["ai_extraction"]
        cols = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'assessment_assignments'"))}
    assert "opened_at" not in cols and "question_set_id" not in cols
    command.upgrade(cfg, "head")


TRACKING = "f4a9c3d7b215"


def test_tracking_upgrade_downgrade(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, TRACKING)
    assert "participant_events" in _tables(engine)
    row = ("INSERT INTO participant_events (id, evaluation_id, event_type, detail, actor, dedupe_key) "
           "VALUES (:id, 'M-3', :t, '{}', 'system', :k)")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, "
                          "instrument_version, regulators, status) VALUES ('M-3', 'Co', 'insurance', 2025, 'DEFAULT', 1, '{}', 'live')"))
        assert conn.execute(text("SELECT reminder_settings FROM evaluations WHERE id = 'M-3'")).scalar() == {}
        conn.execute(text(row), {"id": uuid.uuid4(), "t": "reminder_sent", "k": "a:auto:1"})
        with pytest.raises(Exception):  # a reminder slot can only be recorded once
            with conn.begin_nested():
                conn.execute(text(row), {"id": uuid.uuid4(), "t": "reminder_sent", "k": "a:auto:1"})
        with pytest.raises(Exception):  # unknown event types are refused
            with conn.begin_nested():
                conn.execute(text(row), {"id": uuid.uuid4(), "t": "shredded", "k": None})
    command.downgrade(cfg, PORTAL)
    assert "participant_events" not in _tables(engine)
    command.upgrade(cfg, "head")
