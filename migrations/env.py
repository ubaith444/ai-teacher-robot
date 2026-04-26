import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
from dotenv import load_dotenv

# 1. Get the directory where env.py is (migrations/)
# and navigate up to find the project root and backend dir
this_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(this_dir, ".."))
backend_dir = os.path.join(project_root, "backend")

# 2. Add 'backend' to sys.path so we can import our app
if os.path.exists(backend_dir):
    sys.path.insert(0, backend_dir)
else:
    # Fallback: if we are already in backend, root might be one level up
    sys.path.insert(0, os.getcwd())

# 3. Load environment variables from project root .env
load_dotenv(os.path.join(project_root, ".env"))

# 4. Import our models for autogenerate support
try:
    from app.core.database import Base
    from app.models.models import (
        User, Student, Attendance, Session, Timetable,
        LearningProfile, TopicMastery, InteractionLog, PracticeAttempt, Performance
    )  # noqa: F401
    target_metadata = Base.metadata
except ImportError as e:
    print(f"Warning: Could not import models for autogenerate: {e}")
    import traceback
    traceback.print_exc()
    target_metadata = None

# this is the Alembic Config object
config = context.config

# 5. Set sqlalchemy.url from .env
sync_url = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL")
if sync_url:
    if "postgresql+asyncpg://" in sync_url:
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
