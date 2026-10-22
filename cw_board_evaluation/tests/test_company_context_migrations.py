"""
Migration tests for the company context revisions, on a throwaway database
("<test database>_company_migrations").

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL with CREATEDB rights.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
BEFORE = "77f8a9c3e317"  # sector_code_defaults (section 3)
NEW_TABLES = {
    "organisations", "org_documents", "organisation_facts", "org_committees",
    "organisation_governance_codes", "evaluation_scope_subject_types", "evaluation_context_snapshots",
}


@pytest.fixture
def migration_db(monkeypatch):
    if os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")
    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_company_migrations")
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
    command.downgrade(cfg, BEFORE)
    assert not (NEW_TABLES & _tables(engine))
    with engine.connect() as conn:
        cols = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'evaluations'"
        )).scalars())
    assert "organisation_id" not in cols and {"tenant_name", "sector", "regulators"} <= cols
    command.upgrade(cfg, "head")
    assert NEW_TABLES <= _tables(engine)


def test_backfill_one_organisation_per_tenant(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, BEFORE)
    rows = [
        ("eval-a1", "EMOK Express", "insurance", 2024),
        ("eval-a2", "EMOK Express ", "Insurance ", 2025),   # same tenant (trimmed)
        ("eval-b1", "Beta Microfinance", "Microfinance Bank", 2025),
        ("eval-c1", "Acme Oil", "Oil & Gas", 2025),         # sector doesn't map
    ]
    with engine.begin() as conn:
        for eid, name, sector, year in rows:
            conn.execute(text(
                "INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, instrument_version, "
                "regulators) VALUES (:id, :n, :s, :y, 'DEFAULT', 1, '{}')"
            ), {"id": eid, "n": name, "s": sector, "y": year})

    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        orgs = {r.name: r for r in conn.execute(text("SELECT * FROM organisations"))}
        links = dict(conn.execute(text("SELECT id, organisation_id FROM evaluations")).all())
        legacy = {r.id: (r.tenant_name, r.sector) for r in conn.execute(text("SELECT id, tenant_name, sector FROM evaluations"))}
        scope = dict(conn.execute(text(
            "SELECT evaluation_id, count(*) FROM evaluation_scope_subject_types GROUP BY evaluation_id")).all())
        codes = {(r.name, r.code, r.source) for r in conn.execute(text(
            "SELECT o.name, g.code, g.source FROM organisation_governance_codes g JOIN organisations o ON o.id = g.organisation_id"))}

    assert set(orgs) == {"EMOK Express", "Beta Microfinance", "Acme Oil"}
    assert (orgs["EMOK Express"].sector_key, orgs["EMOK Express"].sector_sub_type) == ("insurance", None)
    assert (orgs["Beta Microfinance"].sector_key, orgs["Beta Microfinance"].sector_sub_type) == ("banking", "microfinance")
    assert orgs["Acme Oil"].sector_key is None
    assert links["eval-a1"] == links["eval-a2"] == orgs["EMOK Express"].id
    assert all(links.values())
    assert legacy["eval-a2"] == ("EMOK Express ", "Insurance ")   # legacy columns untouched
    assert set(scope.values()) == {8} and len(scope) == 4
    assert ("EMOK Express", "NAICOM_2021", "sector_default") in codes
    assert ("Beta Microfinance", "CBN_MFB_2018", "sector_default") in codes
    assert not any(name == "Acme Oil" for name, _, _ in codes)

    # Re-running the backfill (down and up) creates no duplicates
    command.downgrade(cfg, "4b8e2d61c0aa")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM organisations")).scalar_one() == 3
