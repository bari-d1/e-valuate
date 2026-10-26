"""
Migration tests for the taxonomy revisions.

Runs Alembic against a throwaway database named "<test database>_migrations"
(created and dropped here), so the shared integration database is untouched.

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL with CREATEDB rights.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, make_url, text

from app.domain import taxonomy
from app.questionnaires.presets import get_questions_for_preset

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "2fb54b7b8545"
TAGS_REVISION = "5e64dd55411f"  # question tags, before the backfill
SUBJECTS_REVISION = "cd3b2611fb3d"  # evaluation_subjects


def _integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture
def migration_db(monkeypatch):
    if not _integration_enabled():
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_migrations")
    admin = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    except Exception as exc:  # pragma: no cover - environment dependent
        admin.dispose()
        pytest.skip(f"Cannot create migration test database: {exc}")

    url_str = url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url_str)  # alembic/env.py reads this
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


def _count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


NEW_TABLES = {"subject_types", "themes", "evidence_sources", "question_subject_types", "evaluation_subjects"}


def test_upgrade_downgrade_upgrade(migration_db) -> None:
    cfg, engine = migration_db
    # Named revisions (not "head - 1") so later migrations don't change what this tests.
    previous = ScriptDirectory.from_config(cfg).get_revision(SUBJECTS_REVISION).down_revision

    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)

    command.downgrade(cfg, previous)
    assert "evaluation_subjects" not in _tables(engine)
    command.upgrade(cfg, "head")
    assert "evaluation_subjects" in _tables(engine)

    # All the way back to the baseline and up again
    command.downgrade(cfg, BASELINE)
    assert not (NEW_TABLES & _tables(engine))
    with engine.connect() as conn:
        cols = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'questions'"
        )).scalars())
    assert not {"theme_code", "evidence_source_code"} & cols
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)


def test_seed_rows_and_idempotency(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    assert (_count(engine, "subject_types"), _count(engine, "themes"), _count(engine, "evidence_sources")) == (8, 12, 3)

    with engine.begin() as conn:
        conn.execute(text("UPDATE themes SET name = 'Renamed by client' WHERE code = 'STRATEGY'"))

    # Re-running the seed (down past it and up again) keeps edits and adds no duplicates.
    command.downgrade(cfg, "b901df6d51e9")
    command.upgrade(cfg, "head")
    assert _count(engine, "themes") == 12
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM themes WHERE code = 'STRATEGY'")).scalar_one() == "Renamed by client"


def test_migration_seed_matches_domain_vocabulary(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        st = {r.code: (r.name, r.cardinality, r.active) for r in conn.execute(text("SELECT * FROM subject_types"))}
        th = {r.code: r.name for r in conn.execute(text("SELECT code, name FROM themes"))}
        ev = {r.code: r.name for r in conn.execute(text("SELECT code, name FROM evidence_sources"))}
    assert st == {s["code"]: (s["name"], s["cardinality"], 1) for s in taxonomy.SUBJECT_TYPES}
    assert th == {t["code"]: t["name"] for t in taxonomy.THEMES}
    assert ev == {e["code"]: e["name"] for e in taxonomy.EVIDENCE_SOURCES}

    spec = importlib.util.spec_from_file_location(
        "backfill", ROOT / "alembic" / "versions" / "7da1879d8dc2_backfill_question_themes.py"
    )
    backfill = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backfill)
    assert backfill.DIMENSION_TO_THEME == taxonomy.DIMENSION_TO_THEME


def test_backfill_maps_each_preset_dimension(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, TAGS_REVISION)

    rows = get_questions_for_preset("expanded") + [
        {"dimension": "General", "text": "Unmapped dimension", "answer_type": "comment"},
        {"dimension": "  open comments ", "text": "Spacing and case", "answer_type": "comment"},
    ]
    with engine.begin() as conn:
        for q in rows:
            conn.execute(
                text(
                    "INSERT INTO questions (id, template_code, version, dimension, text, answer_type, weight, active) "
                    "VALUES (:id, 'T', 1, :d, :t, :a, 1, 1)"
                ),
                {"id": uuid.uuid4(), "d": q["dimension"], "t": q["text"], "a": q["answer_type"]},
            )

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        got = {r.text: (r.dimension, r.theme_code) for r in conn.execute(text("SELECT text, dimension, theme_code FROM questions"))}

    for q in get_questions_for_preset("expanded"):
        assert got[q["text"]][1] == taxonomy.DIMENSION_TO_THEME[q["dimension"]], q["dimension"]
    assert got["Unmapped dimension"][1] is None
    assert got["Spacing and case"][1] == "GENERAL"
    # dimension itself is untouched
    assert got["Spacing and case"][0] == "  open comments "

    command.downgrade(cfg, TAGS_REVISION)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM questions WHERE theme_code IS NOT NULL")).scalar_one() == 0
