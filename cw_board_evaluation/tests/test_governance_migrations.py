"""
Migration tests for the governance library revisions, on a throwaway database
("<test database>_governance_migrations").

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL with CREATEDB rights.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

from app.domain.governance import GOVERNANCE_CODES, SECTOR_CODE_DEFAULTS

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
BEFORE_GOVERNANCE = "cd3b2611fb3d"  # evaluation_subjects
GOVERNANCE_TABLES = {
    "governance_codes", "governance_clauses", "governance_clause_subject_types",
    "sector_code_defaults", "evaluation_governance_codes",
}


@pytest.fixture
def migration_db(monkeypatch):
    if os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_governance_migrations")
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
    assert GOVERNANCE_TABLES <= _tables(engine)

    command.downgrade(cfg, BEFORE_GOVERNANCE)
    assert not (GOVERNANCE_TABLES & _tables(engine))
    assert "evaluation_subjects" in _tables(engine)

    command.upgrade(cfg, "head")
    assert GOVERNANCE_TABLES <= _tables(engine)


def test_seeded_codes_and_defaults(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        rows = {r.code: r for r in conn.execute(text("SELECT * FROM governance_codes"))}
        defaults = {(r.sector, r.sub_type, r.code) for r in conn.execute(text("SELECT * FROM sector_code_defaults"))}

    assert set(rows) == {c["code"] for c in GOVERNANCE_CODES}
    for spec in GOVERNANCE_CODES:  # migration's frozen copy matches the domain data
        row = rows[spec["code"]]
        for key in ("title", "issuer", "sector", "version", "status", "supplements_code", "source_filename", "notes"):
            assert getattr(row, key) == spec[key], (spec["code"], key)
        assert row.issued_date == spec["issued_date"] and row.effective_date == spec["effective_date"]
        assert row.jurisdiction == "NG" and row.clauses_loaded is False
    assert rows["NAICOM_2021"].effective_date == date(2021, 6, 1)
    assert defaults == set(SECTOR_CODE_DEFAULTS)


def test_seed_migrations_are_idempotent(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(text("UPDATE governance_codes SET notes = 'edited' WHERE code = 'SME_2024'"))
    # Re-run only the seed migrations (sector defaults depend on codes)
    spec = importlib.util.spec_from_file_location("reg", ROOT / "alembic" / "versions" / "9c93e7123f6a_register_governance_codes.py")
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    command.downgrade(cfg, "9c93e7123f6a")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM governance_codes")).scalar_one() == len(reg.GOVERNANCE_CODES)
        assert conn.execute(text("SELECT count(*) FROM sector_code_defaults")).scalar_one() == len(SECTOR_CODE_DEFAULTS)
        assert conn.execute(text("SELECT notes FROM governance_codes WHERE code = 'SME_2024'")).scalar_one() == "edited"
