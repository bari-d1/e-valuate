"""
Migration tests for the director profile revisions, on a throwaway database
("<test database>_director_migrations").

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
BEFORE = "e71c5a09d3b8"  # last company context revision
NEW_TABLES = {"board_members", "board_member_facts", "committee_memberships"}


@pytest.fixture
def migration_db(monkeypatch):
    if os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")
    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_director_migrations")
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


def _columns(engine, table) -> set:
    with engine.connect() as conn:
        return set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table}).scalars())


def test_upgrade_downgrade_upgrade(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)
    assert "board_member_id" in _columns(engine, "participants")
    assert "board_member_id" in _columns(engine, "org_documents")
    assert {"participants", "generation_only"} <= _columns(engine, "evaluation_context_snapshots")

    org_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organisations (id, name, country, profile_status, profile_version) VALUES (:id, 'Roundtrip Plc', 'NG', 'draft', 1)"), {"id": org_id})
        conn.execute(text(
            "INSERT INTO org_documents (id, organisation_id, doc_type, filename, content_type, size_bytes, storage_key, "
            "extraction_status) VALUES (:id, :o, 'director_profile', 'cv.txt', 'text/plain', 1, 'k', 'pending')"), {"id": uuid.uuid4(), "o": org_id})

    command.downgrade(cfg, BEFORE)
    assert not (NEW_TABLES & _tables(engine))
    assert "board_member_id" not in _columns(engine, "participants")
    with engine.connect() as conn:  # director profiles can't survive the old doc_type check
        assert conn.execute(text("SELECT doc_type FROM org_documents")).scalar_one() == "other"
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)


def test_board_member_uniqueness(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    org_id = uuid.uuid4()
    insert = text("INSERT INTO board_members (id, organisation_id, full_name, email, display_code, active, profile_status, profile_version) "
                  "VALUES (:id, :o, 'X', :e, :c, true, 'draft', 1)")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organisations (id, name, country, profile_status, profile_version) VALUES (:id, 'Unique Plc', 'NG', 'draft', 1)"), {"id": org_id})
        conn.execute(insert, {"id": uuid.uuid4(), "o": org_id, "e": "a@x.test", "c": "P001"})
        conn.execute(insert, {"id": uuid.uuid4(), "o": org_id, "e": None, "c": None})
        conn.execute(insert, {"id": uuid.uuid4(), "o": org_id, "e": None, "c": None})  # NULLs don't clash
    for email, code in (("A@X.test", "P002"), ("b@x.test", "P001")):
        with pytest.raises(Exception), engine.begin() as conn:
            conn.execute(insert, {"id": uuid.uuid4(), "o": org_id, "e": email, "c": code})


def test_backfill_merges_people_and_reports(migration_db, capsys) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, BEFORE)
    org_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organisations (id, name, country, profile_status, profile_version) VALUES (:id, 'Backfill Plc', 'NG', 'draft', 1)"), {"id": org_id})
        for eid, year, org in (("eval-old", 2024, org_id), ("eval-new", 2025, org_id), ("eval-orphan", 2025, None)):
            conn.execute(text(
                "INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, instrument_version, "
                "regulators, organisation_id, created_at) VALUES (:id, 'Backfill Plc', 'insurance', :y, 'DEFAULT', 1, "
                "'{}', :o, make_timestamptz(:y, 1, 1, 0, 0, 0))"), {"id": eid, "y": year, "o": org})
        rows = [
            ("eval-old", "member01@demo.test", "Board Member 01", "Chair"),
            ("eval-new", " MEMBER01@demo.test ", "Board Member 01", "INED"),   # same person, messy email
            ("eval-new", "member02@demo.test", "Board Member 02", "Chairman"),  # role doesn't map
            ("eval-orphan", "member03@demo.test", "Board Member 03", "NED"),   # no organisation
        ]
        for eid, email, name, role in rows:
            conn.execute(text(
                "INSERT INTO participants (id, evaluation_id, email, full_name, role, status, created_at) "
                "VALUES (:id, :e, :m, :n, :r, 'invited', now())"),
                {"id": uuid.uuid4(), "e": eid, "m": email, "n": name, "r": role})

    command.upgrade(cfg, "head")
    log = capsys.readouterr().err  # alembic.ini logs to stderr
    assert "'Chairman'" in log and "did not map" in log
    assert "eval-orphan has no organisation" in log

    with engine.connect() as conn:
        members = conn.execute(text("SELECT id, email FROM board_members ORDER BY email")).all()
        links = dict(conn.execute(text("SELECT email, board_member_id FROM participants")).all())
        facts = conn.execute(text("SELECT board_member_id, key, value, status, note FROM board_member_facts")).all()
    assert [m.email for m in members] == ["member01@demo.test", "member02@demo.test"]
    m1 = members[0].id
    assert links["member01@demo.test"] == links[" MEMBER01@demo.test "] == m1
    assert links["member03@demo.test"] is None
    assert len(facts) == 1
    f = facts[0]
    assert (f.board_member_id, f.key, f.value, f.status) == (m1, "governance_role", "ined", "proposed")
    assert "chair (eval-old)" in f.note

    # Re-running (down and up) creates no duplicates
    command.downgrade(cfg, "8a1e47c2d5f0")
    command.downgrade(cfg, "6d2f0b8a91c4")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM board_members")).scalar_one() == 2
        assert conn.execute(text("SELECT count(*) FROM board_member_facts")).scalar_one() == 1
