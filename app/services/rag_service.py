import logging
import httpx
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.legal_knowledge import LegalKnowledgeChunk

logger = logging.getLogger(__name__)

class RAGService:
    """
    Servicio de RAG (Retrieval-Augmented Generation) para Derecho Colombiano.
    
    Gestiona la generación de embeddings, almacenamiento de chunks e indexación 
    de normatividad y jurisprudencia usando pgvector en PostgreSQL.
    """
    
    @staticmethod
    async def get_embedding(text_content: str) -> List[float]:
        """
        Genera el vector de embeddings (3072 dimensiones) usando gemini-embedding-2 de Gemini API.
        """
        api_key = settings.GEMINI_API_KEY or (settings.GEMINI_API_KEYS[0] if settings.GEMINI_API_KEYS else None)
        if not api_key:
            raise ValueError("GEMINI_API_KEY no configurada en settings.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent?key={api_key}"
        payload = {
            "model": "models/gemini-embedding-2",
            "content": {
                "parts": [{"text": text_content}]
            }
        }
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=20.0)
            if res.status_code != 200:
                logger.error(f"Error en Gemini Embedding API ({res.status_code}): {res.text}")
                raise RuntimeError(f"Error generando embedding en Gemini API: {res.text}")
                
            data = res.json()
            vector = data.get("embedding", {}).get("values", [])
            if not vector:
                raise RuntimeError("La API de Gemini retornó una estructura de vector vacía o inválida.")
            return vector

    @staticmethod
    async def add_chunk(
        session: AsyncSession,
        source: str,
        citation: str,
        content: str,
        category: str
    ) -> LegalKnowledgeChunk:
        """
        Genera el embedding e inserta un fragmento normativo o de jurisprudencia en la base de datos.
        """
        vector = await RAGService.get_embedding(content)
        chunk = LegalKnowledgeChunk(
            source=source,
            citation=citation,
            content=content,
            category=category,
            embedding=vector
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)
        logger.info(f"Chunk legal insertado exitosamente: id={chunk.id}, source='{source}', citation='{citation}'")
        return chunk

    @staticmethod
    async def search_semantic(
        session: AsyncSession,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda semántica por similitud de coseno en PostgreSQL con pgvector.
        Calcula la similitud como 1 - (distancia_coseno) utilizando el operador <=> de pgvector.
        """
        query_vector = await RAGService.get_embedding(query)
        
        # Query cruda para cálculo de distancia en pgvector
        sql_query = """
            SELECT id, source, citation, content, category, 
                   1 - (embedding <=> CAST(:vector AS vector)) AS similarity
            FROM legal_knowledge_chunks
            WHERE 1 - (embedding <=> CAST(:vector AS vector)) >= :threshold
        """
        
        params = {
            "vector": str(query_vector),
            "threshold": threshold,
            "limit": limit
        }
        
        if category:
            sql_query += " AND category = :category"
            params["category"] = category
            
        sql_query += " ORDER BY similarity DESC LIMIT :limit;"
        
        res = await session.execute(text(sql_query), params)
        rows = res.fetchall()
        
        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "source": r[1],
                "citation": r[2],
                "content": r[3],
                "category": r[4],
                "similarity": float(r[5])
            })
        
        logger.info(f"Búsqueda semántica para query='{query}' arrojó {len(results)} resultados.")
        return results
