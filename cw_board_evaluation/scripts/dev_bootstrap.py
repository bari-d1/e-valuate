"""
Prepare the local database for ../dev.sh: create it if missing, apply migrations,
and seed demo data the first time (empty database only).

Safe to run on every start: existing data is never changed or removed.
"""
from __future__ import annotations

import os
import subprocess
import sys

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, make_url, text

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(find_dotenv(), override=False)


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=HERE, check=True)


def ensure_database(url_str: str) -> None:
    url = make_url(url_str)
    try:
        create_engine(url).connect().close()
        return
    except Exception as e:
        if f'database "{url.database}" does not exist' not in str(e):
            sys.exit(
                f"Can't connect to Postgres at {url.render_as_string(hide_password=True)}:\n  {e}\n"
                "Check DATABASE_URL in cw_board_evaluation/.env."
            )

    print(f"Creating database {url.database}...")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


def is_empty(url_str: str) -> bool:
    with create_engine(url_str).connect() as conn:
        return conn.execute(text("SELECT count(*) FROM evaluations")).scalar() == 0


def main() -> None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        sys.exit("DATABASE_URL is not set in cw_board_evaluation/.env.")

    ensure_database(url)
    run("-m", "alembic", "upgrade", "head")

    if is_empty(url):
        print("Empty database: seeding demo evaluation eval-002...")
        run("scripts/seed_reference_data.py")
        run("scripts/seed_demo_environment.py", "eval-002")


if __name__ == "__main__":
    main()
