import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.legal_knowledge import LegalKnowledgeChunk
from app.services.rag_service import RAGService
from app.services.scrapers.suin_scraper import SUINScraper
from app.services.scrapers.corte_scraper import CorteScraper
from app.services.scrapers.consejo_scraper import ConsejoScraper

logger = logging.getLogger(__name__)

class LegalIngestionService:
    """
    Servicio de orquestación para la ingesta de normatividad y jurisprudencia colombiana.
    Coordina los scrapers, genera embeddings vectoriales y almacena los chunks en pgvector.
    """

    @staticmethod
    async def chunk_exists(session: AsyncSession, source: str, citation: str) -> bool:
        """
        Verifica si un chunk con el mismo source y citation ya existe en la base de datos.
        """
        stmt = select(LegalKnowledgeChunk).where(
            LegalKnowledgeChunk.source == source,
            LegalKnowledgeChunk.citation == citation
        )
        res = await session.execute(stmt)
        return res.scalars().first() is not None

    @staticmethod
    async def ingest_default_knowledge(session: AsyncSession) -> int:
        """
        Orquesta la ingesta de la base de conocimiento legal colombiana por defecto.
        Ejecuta los scrapers (en modo de fallbacks / local si no se proveen URLs externas)
        y procesa la inserción en lote con embeddings vectoriales de 3072 dimensiones.
        """
        logger.info("Iniciando ingesta de base de conocimiento legal colombiana por defecto...")
        
        # 1. Instanciar scrapers
        suin = SUINScraper()
        corte = CorteScraper()
        consejo = ConsejoScraper()
        
        chunks_to_ingest = []
        
        try:
            # 2. Recopilar datos de SUIN (Leyes, Códigos)
            logger.info("Recopilando datos de SUIN...")
            suin_chunks = await suin.scrape()
            chunks_to_ingest.extend(suin_chunks)
            
            # 3. Recopilar datos de la Corte Constitucional (Sentencias)
            logger.info("Recopilando datos de la Corte Constitucional...")
            corte_chunks = await corte.scrape()
            chunks_to_ingest.extend(corte_chunks)
            
            # 4. Recopilar datos del Consejo de Estado (Providencias)
            logger.info("Recopilando datos del Consejo de Estado...")
            consejo_chunks = await consejo.scrape()
            chunks_to_ingest.extend(consejo_chunks)
            
        finally:
            # Asegurar cierre de conexiones
            await suin.close()
            await corte.close()
            await consejo.close()
            
        logger.info(f"Total de chunks recopilados para evaluación: {len(chunks_to_ingest)}")
        
        ingested_count = 0
        
        # 5. Filtrar duplicados y preparar lote
        unique_items = []
        for item in chunks_to_ingest:
            source = item["source"]
            citation = item["citation"]
            
            # Verificar si ya existe para evitar duplicación
            exists = await LegalIngestionService.chunk_exists(session, source, citation)
            if exists:
                logger.info(f"Saltando chunk duplicado: '{source}' - '{citation}'")
                continue
            unique_items.append(item)
                
        # 6. Insertar en lote usando add_chunks_batch
        if unique_items:
            try:
                inserted_chunks = await RAGService.add_chunks_batch(session, unique_items)
                ingested_count = len(inserted_chunks)
            except Exception as e:
                logger.error(f"Error en ingesta por lote: {e}. Intentando fallback individual...")
                # Fallback individual ante fallos en lote
                for item in unique_items:
                    try:
                        await RAGService.add_chunk(
                            session=session,
                            source=item["source"],
                            citation=item["citation"],
                            content=item["content"],
                            category=item["category"]
                        )
                        ingested_count += 1
                    except Exception as ex:
                        logger.error(f"Error en fallback individual para '{item['source']}': {ex}")
                        
        logger.info(f"Ingesta de conocimiento legal completada. {ingested_count} nuevos registros indexados.")
        return ingested_count

