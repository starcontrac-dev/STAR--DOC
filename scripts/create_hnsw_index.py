import asyncio
import logging
import sys
import os

# Asegurar que el path del proyecto esté en el PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine

# Configurar logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("create_hnsw_index")

async def main():
    logger.info("Iniciando creación de índice HNSW en la base de datos...")
    
    async with engine.begin() as conn:
        # 1. Asegurar extensión pgvector
        try:
            logger.info("Asegurando la extensión 'vector' en PostgreSQL...")
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            logger.info("✓ Extensión 'vector' verificada/creada con éxito.")
        except Exception as e:
            logger.error(f"Error al asegurar la extensión 'vector': {e}")
            logger.info("Intentando proceder de todos modos...")

        # 2. Crear índice HNSW
        try:
            logger.info("Creando índice HNSW 'hnsw_legal_embedding_idx' en la tabla 'legal_knowledge_chunks'...")
            
            # Nota: pgvector >= 0.5.0 es requerido para HNSW.
            # Usamos WITH (m = 16, ef_construction = 64) como hiperparámetros balanceados de velocidad/precisión.
            sql_create_index = """
                CREATE INDEX IF NOT EXISTS hnsw_legal_embedding_idx 
                ON legal_knowledge_chunks 
                USING hnsw (embedding vector_cosine_ops) 
                WITH (m = 16, ef_construction = 64);
            """
            await conn.execute(text(sql_create_index))
            logger.info("✓ Índice HNSW 'hnsw_legal_embedding_idx' creado exitosamente.")
            
        except Exception as e:
            logger.error(f"Fallo al crear el índice HNSW: {e}")
            logger.warning(
                "Es posible que la versión de pgvector en tu base de datos local sea inferior a la 0.5.0 "
                "o que no tenga soporte compilado para HNSW. En ese caso, la base de datos seguirá haciendo "
                "búsquedas secuenciales funcionales, pero se recomienda actualizar pgvector en producción."
            )
            
    await engine.dispose()
    logger.info("Cerrando conexión de base de datos. Proceso finalizado.")

if __name__ == "__main__":
    asyncio.run(main())
