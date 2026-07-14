import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.core.config import settings

# --- Configuración de Logging ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Configuración del Engine (SQLAlchemy/SQLModel) ---
# Usamos asyncpg driver. DATABASE_URL debe ser postgresql+asyncpg://...
db_url = settings.DATABASE_URL
if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

if not db_url:
    raise ValueError("DATABASE_URL no está configurada")

engine = create_async_engine(
    db_url,
    echo=False, # Pon True para debug SQL
    future=True
)

# --- Configuración de la Sesión ---
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para FastAPI que provee una sesión de base de datos."""
    async with async_session_maker() as session:
        yield session

async def init_db():
    """Inicializa la base de datos (crea tablas si no existen). 
    Útil para dev, pero en prod usamos Alembic."""
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # NO descomentar en prod
        await conn.run_sync(SQLModel.metadata.create_all)

# --- Funciones Legacy (para mantener compatibilidad mientras refactorizamos) ---
# Una vez refactorizado todo, estas funciones deberían desaparecer.

import asyncpg

async def get_db_connection():
    """Abre y devuelve una conexión nueva a la base de datos (Legacy asyncpg)."""
    # Usamos la URL original de asyncpg (sin +asyncpg)
    raw_url = settings.DATABASE_URL
    try:
        conn = await asyncpg.connect(dsn=raw_url)
        return conn
    except Exception as e:
        log.error(f"No se pudo conectar a la base de datos (Legacy): {e}")
        raise

async def close_db_connection(connection):
    """Cierra la conexión proporcionada (Legacy asyncpg)."""
    try:
        await connection.close()
    except Exception as e:
        log.warning(f"Error cerrando la conexión de la base de datos (Legacy): {e}")

async def connect_to_db():
    """Operación de compatibilidad e inicialización de tablas."""
    log.info("connect_to_db: Inicializando Engine SQLModel...")
    try:
        await init_db()
        log.info("Tablas de la base de datos inicializadas/verificadas.")
    except Exception as e:
        log.error(f"Error inicializando tablas en connect_to_db: {e}")


async def close_db_pool():
    """Cierra el engine."""
    log.info("Cerrando Engine SQLModel...")
    await engine.dispose()
