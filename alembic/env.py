import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# Import your Base and all models to ensure they're registered
from userapp.core.models.main import Base
from userapp.core.models.tables import (
    Group, Note, Project, SubmitNode, User, UserGroup,
    UserNote, UserProject, UserSubmit, Token, Access
)
from userapp.core.models.views import JoinedProjectView, UserSubmitNodesView  # Import views if needed

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Custom: Should you include this table in autogenerate?
    """
    # Exclude views from autogenerate
    if type_ == "table" and hasattr(object, 'info'):
        if object.info.get('is_view'):
            return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = os.environ.get("DB_URL") or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get configuration section and override sqlalchemy.url with environment variable
    configuration = config.get_section(config.config_ini_section, {})
    db_url = os.environ.get("DB_URL")
    if db_url:
        # Ensure async driver is used
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        configuration["sqlalchemy.url"] = db_url

    else:
        if db_url is None:
            DB_USER = os.environ.get("DB_USER")
            DB_PASSWORD = os.environ.get("DB_PASSWORD")
            DB_HOST = os.environ.get("DB_HOST")
            DB_PORT = os.environ.get("DB_PORT", "5432")
            DB_NAME = os.environ.get("DB_NAME")

            configuration["sqlalchemy.url"] = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"ssl": os.environ.get("PYTHON_ENV") == "production"}
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
