"""
Migration tests for the analysis revisions after the first one, on a throwaway
database ("<test database>_analysis_migrations") holding findings written before
each change.

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
ANALYSIS = "c68ecb986b88"
PRACTICE_GAP = "d1a6f0c3e8b2"


@pytest.fixture
def migration_db(monkeypatch):
    if os.getenv("RUN_INTEGRATION_TESTS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests")

    base_url = make_url(os.environ["DATABASE_URL"])
    url = base_url.set(database=f"{base_url.database}_analysis_migrations")
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


def _seed_run(engine) -> uuid.UUID:
    """An evaluation with one finished analysis run; returns the run id."""
    run_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO evaluations (id, tenant_name, sector, year, instrument_template_code, instrument_version, regulators) "
            "VALUES ('MIG-A', 'Migration Co', 'insurance', 2026, 'DEFAULT', 1, '{}')"))
        conn.execute(text(
            "INSERT INTO analysis_runs (id, evaluation_id, status, settings, inputs, results, created_by) "
            "VALUES (:id, 'MIG-A', 'done', '{\"min_raters\": 3}', '{}', '{}', 'Consultant A')"), {"id": run_id})
    return run_id


def _add_finding(engine, run_id, *, kind: str, status: str = "draft", rule=None, origin: str = "computed",
                 statement: str = "A finding.") -> uuid.UUID:
    fid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO findings (id, run_id, kind, statement, support, origin, status, original_text, rule) "
            "VALUES (:id, :run, :kind, :st, 'moderate', :origin, :status, :st, :rule)"),
            {"id": fid, "run": run_id, "kind": kind, "st": statement, "origin": origin, "status": status, "rule": rule})
    return fid


def _finding(engine, fid):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM findings WHERE id = :id"), {"id": fid}).mappings().one()


def test_compliance_gaps_become_practice_gaps_and_back(migration_db) -> None:
    cfg, engine = migration_db
    command.upgrade(cfg, ANALYSIS)
    run_id = _seed_run(engine)
    gap = _add_finding(engine, run_id, kind="compliance_gap", rule="compliance_shortfall",
                       statement="Answered \"No\" to \"Is there an induction programme?\".")
    other = _add_finding(engine, run_id, kind="concern", rule="theme_concern")

    command.upgrade(cfg, PRACTICE_GAP)
    row = _finding(engine, gap)
    assert (row["kind"], row["rule"]) == ("practice_gap", "practice_differs")
    assert row["statement"] == "Answered \"No\" to \"Is there an induction programme?\"."  # text kept
    assert _finding(engine, other)["kind"] == "concern"
    with pytest.raises(Exception, match="ck_findings_kind"):
        _add_finding(engine, run_id, kind="compliance_gap")

    command.downgrade(cfg, ANALYSIS)
    row = _finding(engine, gap)
    assert (row["kind"], row["rule"]) == ("compliance_gap", "compliance_shortfall")
    with pytest.raises(Exception, match="ck_findings_kind"):
        _add_finding(engine, run_id, kind="practice_gap")

    command.upgrade(cfg, "head")
    assert _finding(engine, gap)["kind"] == "practice_gap"
