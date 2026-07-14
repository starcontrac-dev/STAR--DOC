import asyncio
import logging
import sys
import os

# Añadir el directorio raíz al path de Python para poder importar 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

async def run_migration():
    logger.info("Iniciando migración de la tabla user_documents en PostgreSQL...")
    try:
        async with engine.begin() as conn:
            # 1. Agregar columna cryptpad_share_url
            logger.info("Verificando/Agregando columna cryptpad_share_url...")
            await conn.execute(text(
                "ALTER TABLE user_documents ADD COLUMN IF NOT EXISTS cryptpad_share_url VARCHAR(1000) DEFAULT NULL;"
            ))
            
            # 2. Agregar columna is_collaborative
            logger.info("Verificando/Agregando columna is_collaborative...")
            await conn.execute(text(
                "ALTER TABLE user_documents ADD COLUMN IF NOT EXISTS is_collaborative BOOLEAN DEFAULT FALSE;"
            ))
            
            # 3. Crear índice en is_collaborative
            logger.info("Verificando/Creando índice idx_user_documents_is_collaborative...")
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_user_documents_is_collaborative ON user_documents (is_collaborative);"
            ))
            
        logger.info("✅ Migración completada con éxito. Las columnas colaborativas han sido configuradas.")
    except Exception as e:
        logger.error(f"❌ Error durante la migración: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_migration())
