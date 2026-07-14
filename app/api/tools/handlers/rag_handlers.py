import logging
from app.api.tools.registry import register_tool
from app.services.rag_service import RAGService
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

@register_tool("buscar_normatividad_colombiana")
async def handle_buscar_normatividad_colombiana(args: dict, session: AsyncSession, username: str = "Anonimo") -> dict:
    """
    Handler para buscar normatividad y jurisprudencia colombiana en el almacén vectorial pgvector.
    
    Args:
        args: Argumentos enviados por Gemini (query, category, limit).
        session: Sesión asíncrona de base de datos.
        username: Usuario que ejecuta la consulta.
        
    Returns:
        dict: Listado de resultados con similitud coseno.
    """
    query = args.get("query")
    category = args.get("category")
    limit = args.get("limit", 3)
    
    logger.info(f"Handler buscar_normatividad_colombiana ejecutado. Query='{query}', Category='{category}', Limit={limit}")
    
    if not query:
        return {"error": "El argumento 'query' es obligatorio."}
        
    try:
        results = await RAGService.search_semantic(
            session=session,
            query=query,
            category=category,
            limit=limit,
            threshold=0.45
        )
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"Error en handle_buscar_normatividad_colombiana: {e}", exc_info=True)
        return {"status": "error", "error": f"Error en búsqueda RAG: {str(e)}"}


@register_tool("guardar_norma_o_sentencia")
async def handle_guardar_norma_o_sentencia(args: dict, session: AsyncSession, username: str = "Anonimo") -> dict:
    """
    Handler para segmentar, generar embeddings e indexar una nueva ley o sentencia en pgvector.
    
    Args:
        args: Argumentos con 'source', 'citation', 'content' y 'category'.
        session: Sesión asíncrona de base de datos.
        username: Usuario que ejecuta la acción.
    """
    source = args.get("source")
    citation = args.get("citation")
    content = args.get("content")
    category = args.get("category", "jurisprudencia")
    
    logger.info(f"Handler guardar_norma_o_sentencia invocado por {username}. Fuente='{source}', Categoría='{category}'")
    
    if not source or not content:
        return {"status": "error", "error": "Los campos 'source' y 'content' son obligatorios."}
        
    try:
        from scripts.import_notebooklm_to_pgvector import smart_chunk_text
        
        # Segmentar texto en chunks semánticos
        chunks = smart_chunk_text(content, chunk_size=1000, overlap=150)
        logger.info(f"Segmentado en {len(chunks)} fragmentos para indexar.")
        
        inserted_count = 0
        for chunk in chunks:
            await RAGService.add_chunk(
                session=session,
                source=source,
                citation=citation or source,
                content=chunk,
                category=category
            )
            inserted_count += 1
            
        return {
            "status": "success",
            "message": f"Se ha registrado y indexado exitosamente '{source}' en la base de datos local.",
            "chunks_inserted": inserted_count
        }
    except Exception as e:
        logger.error(f"Error en handle_guardar_norma_o_sentencia: {e}", exc_info=True)
        return {"status": "error", "error": f"Error registrando norma/sentencia: {str(e)}"}
