"""
Dev helper: ensure database cw_board_eval_baseline exists and reset its public schema
(empty tables). Use before `alembic revision --autogenerate` when you need a clean diff.

Override with BASELINE_DB_NAME, POSTGRES_URL (admin connection to `postgres` db).
"""
import os

import sqlalchemy as sa

admin_url = (os.getenv("POSTGRES_ADMIN_URL") or "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres").strip()
db_name = (os.getenv("BASELINE_DB_NAME") or "cw_board_eval_baseline").strip()

engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
with engine.connect() as conn:
    r = conn.execute(sa.text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")).fetchone()
    if not r:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
        print(f"Created database {db_name}")

url_db = admin_url.rsplit("/", 1)[0] + f"/{db_name}"
engine2 = sa.create_engine(url_db, isolation_level="AUTOCOMMIT")
with engine2.connect() as conn:
    conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
    conn.execute(sa.text("CREATE SCHEMA public"))
    conn.execute(sa.text("GRANT ALL ON SCHEMA public TO postgres"))
    conn.execute(sa.text("GRANT ALL ON SCHEMA public TO public"))
print(f"Reset public schema in {db_name} (empty)")
