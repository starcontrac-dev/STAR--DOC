"""
Handlers de herramientas de búsqueda web.

Herramientas:
- web_search: Busca información actualizada vía Brave Search API
"""

import os
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("web_search")
async def handle_web_search(args: dict, session: AsyncSession, username: str) -> dict:
    """Busca información actualizada en internet usando Brave Search API."""
    query = args.get("query")
    max_results = args.get("max_results", 5)
    if not query:
        return {"error": "Falta query de búsqueda"}

    try:
        # Usar Brave Search API directamente via httpx
        brave_api_key = os.getenv("BRAVE_API_KEY")
        
        if not brave_api_key:
            # Fallback: sin API key configurada
            return {
                "query": query,
                "results": [],
                "message": "⚠️ Búsqueda web no configurada. No se encontró BRAVE_API_KEY en variables de entorno. Responde con tu conocimiento actual o pide al usuario que proporcione información específica.",
                "note": "Para habilitar búsqueda web, agrega BRAVE_API_KEY al archivo .env"
            }
        
        # Hacer búsqueda con Brave API
        async with httpx.AsyncClient() as search_client:
            response = await search_client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_api_key
                },
                params={
                    "q": query,
                    "count": min(max_results, 10),
                    "freshness": "pd"  # Último día para info actual
                },
                timeout=10.0
            )
            response.raise_for_status()
            search_data = response.json()
            
            # Extraer resultados
            web_results = search_data.get("web", {}).get("results", [])
            
            formatted_results = []
            for i, result in enumerate(web_results, 1):
                formatted_results.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "description": result.get("description", ""),
                    "position": i
                })
            
            if not formatted_results:
                return {"results": [], "message": f"No se encontraron resultados para: {query}"}
            
            return {
                "query": query,
                "results_count": len(formatted_results),
                "results": formatted_results,
                "message": f"✅ Búsqueda exitosa. Se encontraron {len(formatted_results)} resultados actuales. Usa esta información para responder al usuario con datos actualizados."
            }
    except Exception as e:
        logger.error(f"Error en búsqueda web: {e}")
        return {"error": f"Error buscando en internet: {str(e)}"}
