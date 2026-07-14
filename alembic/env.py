import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from sqlmodel import SQLModel

# Import application specific config/models
from app.core.config import settings
from app.models import * # Import all models here so Alembic can see them

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Overwrite the sqlalchemy.url in the config object
original_url = settings.DATABASE_URL
if original_url:
    # Ensure async driver
    if original_url.startswith("postgresql://"):
         original_url = original_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # ConfigParser tries to interpolate %, so we need to escape it if it appears in password
    config.set_main_option("sqlalchemy.url", original_url.replace("%", "%%"))

# target_metadata is your metadata
target_metadata = SQLModel.metadata

def include_object(object, name, type_, reflected, compare_to):
    """
    Controla qué objetos (tablas, índices) debe auditar Alembic.
    Ignoramos tablas históricas o de terceros para que no intente borrarlas.
    """
    ignorar_tablas = {
        "apscheduler_jobs", # Gestionada por APScheduler
        "chat_sessions",    # Histórico
        "chat_messages",    # Histórico
        "userdocument",     # Renombrado a user_documents
    }
    if type_ == "table" and name in ignorar_tablas:
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
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
