"""
Alembic environment — uses the same DATABASE_URL as the FastAPI app.

Run (from project root, with DATABASE_URL set):
  alembic revision --autogenerate -m "describe change"
  alembic upgrade head
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import engine_from_config, pool

from alembic import context

load_dotenv(find_dotenv(), override=False)

from app.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise ValueError(
            "DATABASE_URL must be set for Alembic (same as the FastAPI app). "
            "Example: postgresql+psycopg://postgres:postgres@localhost:5432/cw_board_eval"
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (optional)."""
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against DATABASE_URL."""
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
