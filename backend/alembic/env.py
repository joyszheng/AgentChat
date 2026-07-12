"""Alembic environment.

Reuses the application's ``DATABASE_URL`` and ``Base.metadata`` so migrations
always target the same database the app talks to. Run from the ``backend``
directory, e.g. ``uv run alembic upgrade head``.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the ``app`` package importable regardless of the current directory.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Importing app.database loads .env and resolves DATABASE_URL; importing
# app.models registers every table on Base.metadata for autogenerate.
from app.database import DATABASE_URL, Base  # noqa: E402
import app.models  # noqa: E402,F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Force the application's resolved URL, ignoring the placeholder in alembic.ini.
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = DATABASE_URL
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
