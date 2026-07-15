import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env
load_dotenv()

# Asegurar que el path del proyecto esté en el PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from sqlalchemy import text
from app.database import engine, init_db, async_session_maker
from app.services.legal_ingestion_service import LegalIngestionService

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("recreate_legal_knowledge_table")

async def main():
    logger.info("Iniciando recreación de tabla legal_knowledge_chunks...")
    
    # 1. Hacer Drop Table en caliente
    async with engine.begin() as conn:
        try:
            logger.info("Ejecutando DROP TABLE CASCADE en 'legal_knowledge_chunks'...")
            await conn.execute(text("DROP TABLE IF EXISTS legal_knowledge_chunks CASCADE;"))
            logger.info("✓ Tabla eliminada con éxito.")
        except Exception as e:
            logger.error(f"Error eliminando la tabla: {e}")
            sys.exit(1)
            
    # 2. Inicializar base de datos (recreará la tabla con Vector(1536) e índice HNSW)
    try:
        logger.info("Recreando la estructura de tablas a través de SQLModel init_db()...")
        await init_db()
        logger.info("✓ Tablas inicializadas e índice HNSW configurado con éxito.")
    except Exception as e:
        logger.error(f"Error inicializando tablas: {e}")
        sys.exit(1)

    # 3. Ingerir la base de conocimiento legal en lote
    try:
        logger.info("Lanzando la ingesta de conocimiento por defecto en lotes (1536 dimensiones)...")
        async with async_session_maker() as session:
            count = await LegalIngestionService.ingest_default_knowledge(session)
            logger.info(f"✓ Ingesta completada con éxito. Total chunks insertados: {count}")
    except Exception as e:
        logger.error(f"Error en la ingesta: {e}")
        sys.exit(1)
        
    await engine.dispose()
    logger.info("Proceso de recreación e ingesta finalizado con éxito.")

if __name__ == "__main__":
    asyncio.run(main())
