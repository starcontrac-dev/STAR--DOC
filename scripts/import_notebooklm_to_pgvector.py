import asyncio
import sys
import os
import re
import logging
from typing import List, Dict, Any

# Asegurar path de importación del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker
from app.services.notebooklm_service import notebooklm_service
from app.services.rag_service import RAGService
from app.models.legal_knowledge import LegalKnowledgeChunk
from sqlalchemy import select

# Configurar logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("import_notebooklm_pgvector")


def smart_chunk_text(text: str, chunk_size: int = 1000, overlap: int = 150) -> List[str]:
    """
    Segmenta el texto de forma inteligente respetando la estructura de párrafos y oraciones.
    Si un párrafo es demasiado largo, se subdivide por oraciones, y si estas exceden el límite, por caracteres.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_len = 0
    
    for para in paragraphs:
        # Si un solo párrafo excede el tamaño máximo, lo procesamos por oraciones
        if len(para) > chunk_size:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            
            # Dividir párrafo en oraciones usando regex
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                if len(sentence) > chunk_size:
                    # Fallback extremo: dividir por caracteres
                    for i in range(0, len(sentence), chunk_size - overlap):
                        chunks.append(sentence[i:i + chunk_size])
                else:
                    if current_len + len(sentence) > chunk_size:
                        if current_chunk:
                            chunks.append(" ".join(current_chunk))
                            # Reconstruir overlap
                            overlap_chunk = []
                            overlap_len = 0
                            for s_back in reversed(current_chunk):
                                if overlap_len + len(s_back) < overlap:
                                    overlap_chunk.insert(0, s_back)
                                    overlap_len += len(s_back)
                                else:
                                    break
                            current_chunk = overlap_chunk
                            current_len = overlap_len
                    current_chunk.append(sentence)
                    current_len += len(sentence)
        else:
            if current_len + len(para) > chunk_size:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    # Reconstruir overlap
                    overlap_chunk = []
                    overlap_len = 0
                    for p_back in reversed(current_chunk):
                        if overlap_len + len(p_back) < overlap:
                            overlap_chunk.insert(0, p_back)
                            overlap_len += len(p_back)
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_len = overlap_len
            current_chunk.append(para)
            current_len += len(para)
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    return [c for c in chunks if c.strip()]


def infer_category(title: str) -> str:
    """
    Infiere la categoría jurídica a partir del título o las etiquetas del cuaderno.
    """
    title_lower = title.lower()
    if "civil" in title_lower:
        return "civil"
    elif "comercial" in title_lower or "sociedades" in title_lower or "contratos mercantiles" in title_lower:
        return "comercial"
    elif "constitucional" in title_lower or "derechos fundamentales" in title_lower:
        return "constitucional"
    elif "administrativo" in title_lower or "ley 1437" in title_lower or "cpaca" in title_lower:
        return "administrativo"
    elif "tributario" in title_lower or "estatuto tributario" in title_lower:
        return "tributario"
    elif "crypto" in title_lower or "fintech" in title_lower or "cripto" in title_lower:
        return "crypto"
    elif "consumidor" in title_lower or "ley 1480" in title_lower:
        return "consumidor"
    elif "juris" in title_lower or "jurisprudencia" in title_lower or "sentencia" in title_lower:
        return "jurisprudencia"
    else:
        return "general"


async def check_chunk_exists(session, source: str, content: str) -> bool:
    """
    Verifica de manera idempotente si un fragmento idéntico ya está indexado.
    """
    stmt = select(LegalKnowledgeChunk).where(
        LegalKnowledgeChunk.source == source,
        LegalKnowledgeChunk.content == content
    )
    result = await session.execute(stmt)
    return result.scalars().first() is not None


async def import_notebooks_to_db(
    dry_run: bool = False,
    limit_notebooks: int = None,
    limit_sources: int = None,
    limit_chunks: int = None
):
    """
    Obtiene todos los cuadernos con etiquetas #legal y #juris, extrae sus fuentes y
    las almacena en PostgreSQL local con embeddings pgvector.
    """
    print("=" * 70)
    print(" STAR-DOC: IMPORTADOR DE CONOCIMIENTO DE NOTEBOOKLM A PGVECTOR")
    print(f" Modo: {'PRUEBA EN SECO (DRY RUN)' if dry_run else 'IMPORTACIÓN REAL'}")
    if limit_notebooks:
        print(f" Límite de Cuadernos: {limit_notebooks}")
    if limit_sources:
        print(f" Límite de Fuentes por Cuaderno: {limit_sources}")
    if limit_chunks:
        print(f" Límite de Chunks por Fuente: {limit_chunks}")
    print("=" * 70)

    # 1. Obtener cuadernos desde el MCP
    logger.info("Listando cuadernos en NotebookLM...")
    nb_res = await notebooklm_service.list_notebooks()
    if isinstance(nb_res, dict) and "error" in nb_res:
        logger.error(f"Error listando cuadernos desde el MCP: {nb_res['error']}")
        return
        
    notebooks = nb_res.get("notebooks", [])
    logger.info(f"Se encontraron {len(notebooks)} cuadernos en total.")

    # 2. Filtrar cuadernos relevantes (#legal o #juris)
    relevant_notebooks = []
    for nb in notebooks:
        title = nb.get("title", "")
        # Filtrar por etiquetas en el título (ej: [#legal-civil], [#juris-corte_constitucional])
        if "[#legal" in title or "[#juris" in title:
            relevant_notebooks.append(nb)

    logger.info(f"Cuadernos jurídicos filtrados para importar: {len(relevant_notebooks)}")
    
    # Aplicar límite de cuadernos si está definido
    if limit_notebooks:
        relevant_notebooks = relevant_notebooks[:limit_notebooks]
        logger.info(f"Aplicando límite: se procesarán los primeros {len(relevant_notebooks)} cuadernos.")

    for i, nb in enumerate(relevant_notebooks, 1):
        print(f"  {i}. Title: {nb['title']} (ID: {nb['id']}, Sources: {nb['source_count']})")
    
    if not relevant_notebooks:
        logger.warning("No se encontraron cuadernos relevantes etiquetados con #legal o #juris.")
        return

    # 3. Procesar cada cuaderno
    async with async_session_maker() as session:
        for idx, nb in enumerate(relevant_notebooks, 1):
            nb_id = nb["id"]
            nb_title = nb["title"]
            category = infer_category(nb_title)
            
            logger.info(f"\n--- Procesando [{idx}/{len(relevant_notebooks)}]: {nb_title} (Categoría: {category}) ---")
            
            # Obtener detalles del cuaderno con la lista de fuentes
            details = await notebooklm_service.get_notebook(nb_id)
            if isinstance(details, dict) and "error" in details:
                logger.error(f"Error obteniendo fuentes del cuaderno {nb_id}: {details['error']}")
                continue
                
            sources = details.get("sources", [])
            logger.info(f"Cuaderno tiene {len(sources)} fuentes.")
            
            # Aplicar límite de fuentes
            if limit_sources:
                sources = sources[:limit_sources]
                logger.info(f"Aplicando límite de fuentes: se procesarán {len(sources)} fuentes.")
            
            for s_idx, src in enumerate(sources, 1):
                src_id = src["id"]
                src_title = src["title"]
                
                logger.info(f"  -> Leyendo fuente [{s_idx}/{len(sources)}]: {src_title}...")
                
                # Obtener el contenido crudo de la fuente
                content_res = await notebooklm_service.get_source_content(src_id)
                if isinstance(content_res, dict) and "error" in content_res:
                    logger.error(f"     Error obteniendo contenido de la fuente {src_id}: {content_res['error']}")
                    continue
                    
                raw_text = content_res.get("content", "")
                if not raw_text:
                    logger.warning(f"     Fuente {src_title} no contiene texto o está vacía.")
                    continue
                
                # Segmentar texto
                chunks = smart_chunk_text(raw_text, chunk_size=1000, overlap=150)
                logger.info(f"     Texto de {len(raw_text)} caracteres segmentado en {len(chunks)} chunks.")
                
                # Aplicar límite de chunks
                if limit_chunks:
                    chunks = chunks[:limit_chunks]
                    logger.info(f"     Aplicando límite de chunks: se procesarán {len(chunks)} chunks.")
                
                if dry_run:
                    # Mostrar primeros 2 chunks como ejemplo
                    for c_num, chunk in enumerate(chunks[:2], 1):
                        print(f"     [DRY RUN CHUNK {c_num} - {len(chunk)} chars]: {chunk[:100]}...")
                    continue
                
                # Guardar chunks en la BD
                inserted_count = 0
                skipped_count = 0
                
                for c_idx, chunk_text in enumerate(chunks, 1):
                    # Verificar si ya existe para evitar duplicación
                    exists = await check_chunk_exists(session, source=src_title, content=chunk_text)
                    if exists:
                        skipped_count += 1
                        continue
                    
                    try:
                        # Insertar y generar embedding
                        await RAGService.add_chunk(
                            session=session,
                            source=src_title,
                            citation=nb_title,
                            content=chunk_text,
                            category=category
                        )
                        inserted_count += 1
                        
                        # Throttling de API de embeddings para evitar Rate Limits (100ms)
                        await asyncio.sleep(0.1)
                        
                    except Exception as e:
                        logger.error(f"     Error indexando chunk {c_idx}/{len(chunks)}: {e}")
                        # En caso de error de límite de tasa, pausa más prolongada
                        if "quota" in str(e).lower() or "rate" in str(e).lower():
                            logger.warning("     Pausa de 5 segundos debido a cuotas de API de embeddings...")
                            await asyncio.sleep(5)
                
                logger.info(f"     Terminado: {inserted_count} chunks insertados, {skipped_count} omitidos por duplicado.")

    print("\n" + "=" * 70)
    print(" ¡PROCESO DE SINCRONIZACIÓN DE CONOCIMIENTO FINALIZADO!")
    print("=" * 70)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Importar fuentes de NotebookLM a pgvector (PostgreSQL).")
    parser.add_argument("--run", action="store_true", help="Realizar la importación real en la base de datos.")
    parser.add_argument("--limit-notebooks", type=int, default=None, help="Límite máximo de cuadernos a procesar.")
    parser.add_argument("--limit-sources", type=int, default=None, help="Límite máximo de fuentes a procesar por cuaderno.")
    parser.add_argument("--limit-chunks", type=int, default=None, help="Límite máximo de fragmentos a procesar por fuente.")
    
    args = parser.parse_args()
    
    asyncio.run(import_notebooks_to_db(
        dry_run=not args.run,
        limit_notebooks=args.limit_notebooks,
        limit_sources=args.limit_sources,
        limit_chunks=args.limit_chunks
    ))

