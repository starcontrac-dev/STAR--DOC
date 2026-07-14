import os
import sys
import asyncio
import logging

# Configurar path para importar desde la raíz del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Cargar dotenv para las claves API y la BD
from dotenv import load_dotenv
load_dotenv()

from app.database import connect_to_db, close_db_pool, async_session_maker
from app.services.legal_ingestion_service import LegalIngestionService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("scripts.ingest_legal")

async def main():
    logger.info("Iniciando script de ingesta de conocimiento legal colombiano...")
    
    # Inicializar pool de base de datos y verificar tablas
    try:
        await connect_to_db()
    except Exception as e:
        logger.error(f"Error inicializando la base de datos: {e}")
        return

    # Ingestar conocimiento por defecto
    try:
        async with async_session_maker() as session:
            count = await LegalIngestionService.ingest_default_knowledge(session)
            logger.info(f"✨ Éxito: Se indexaron {count} nuevos registros en pgvector.")
    except Exception as e:
        logger.error(f"Error ejecutando la ingesta legal: {e}")
    finally:
        # Cerrar el pool de base de datos
        logger.info("Cerrando conexiones de base de datos...")
        await close_db_pool()
        logger.info("Proceso finalizado.")

if __name__ == "__main__":
    asyncio.run(main())
