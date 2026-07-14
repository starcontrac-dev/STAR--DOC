"""
Handlers de herramientas NLP para análisis de documentos legales.

Herramientas:
- analizar_contrato: Análisis completo de un contrato con NLP
- extraer_entidades_documento: Extracción de entidades nombradas (NER)
- detectar_clausulas_documento: Detección de cláusulas contractuales
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("analizar_contrato")
async def handle_analizar_contrato(args: dict, session: AsyncSession, username: str) -> dict:
    """Analiza un contrato o documento legal completo con NLP."""
    try:
        from app.core.tools.analizador_documentos import analizar_contrato as analizar_contrato_fn
        texto = args.get("texto")
        file_path = args.get("file_path")
        return await analizar_contrato_fn(texto=texto, file_path=file_path)
    except Exception as e:
        logger.error(f"Error en analizar_contrato: {e}")
        return {"error": f"Error analizando contrato: {str(e)}"}


@register_tool("extraer_entidades_documento")
async def handle_extraer_entidades_documento(args: dict, session: AsyncSession, username: str) -> dict:
    """Extrae entidades nombradas (NER) de un texto legal."""
    try:
        from app.core.tools.analizador_documentos import extraer_entidades_documento as extraer_entidades_fn
        texto = args.get("texto", "")
        max_entidades = args.get("max_entidades", 50)
        return extraer_entidades_fn(texto=texto, max_entidades=max_entidades)
    except Exception as e:
        logger.error(f"Error en extraer_entidades_documento: {e}")
        return {"error": f"Error extrayendo entidades: {str(e)}"}


@register_tool("detectar_clausulas_documento")
async def handle_detectar_clausulas_documento(args: dict, session: AsyncSession, username: str) -> dict:
    """Detecta cláusulas contractuales presentes y faltantes en un contrato."""
    try:
        from app.core.tools.analizador_documentos import detectar_clausulas_documento as detectar_clausulas_fn
        texto = args.get("texto", "")
        return detectar_clausulas_fn(texto=texto)
    except Exception as e:
        logger.error(f"Error en detectar_clausulas_documento: {e}")
        return {"error": f"Error detectando cláusulas: {str(e)}"}
