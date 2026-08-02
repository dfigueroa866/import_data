import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, pool, text

from alembic import context


# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Load environment variables from .env (override stale shell vars)
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env", override=True)
except ImportError:
    pass

# Import only the Base class to avoid import issues
try:
    from src.data_staging.models.base import Base
except ImportError:
    # Try alternative import path
    from data_staging.models.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from app settings or environment."""
    try:
        from data_staging.config import settings
        return str(settings.DATABASE_URL)
    except Exception:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return database_url

    raise RuntimeError(
        "DATABASE_URL no configurada. Verifica m8_connect/.env o exporta la variable."
    )


def _is_local_database_url(database_url: str) -> bool:
    hostname = (urlparse(database_url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _create_connectable(database_url: str):
    """Engine de migraciones alineado con database.py (sin SSL en túnel local)."""
    connect_args = {"connect_timeout": 10}
    if _is_local_database_url(database_url):
        connect_args["sslmode"] = "disable"
    return create_engine(
        database_url,
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="staging_meta",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    database_url = get_url()
    configuration["sqlalchemy.url"] = database_url

    connectable = _create_connectable(database_url)

    with connectable.connect() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS staging_meta"))
        connection.commit()

        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            version_table_schema="staging_meta",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()