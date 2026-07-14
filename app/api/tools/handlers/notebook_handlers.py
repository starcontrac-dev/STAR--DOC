"""
Handlers de herramientas NotebookLM Legal (Base de Conocimiento Jurídico).

Herramientas:
- notebook_query_legal: Consulta la base de conocimiento jurídico
- notebook_list_tagged: Lista cuadernos por etiqueta
- notebook_create_legal: Crea cuaderno legal nuevo
- notebook_add_source: Agrega fuente a un cuaderno
- notebook_research_legal: Investigación legal automatizada
- notebook_research_existing: Investigación en cuaderno existente
- notebook_status: Estado general de NotebookLM
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import register_tool

logger = logging.getLogger(__name__)

# --- Importación segura de las funciones de NotebookLM ---
try:
    from app.core.skills.library.notebooklm_legal.tools import (
        notebook_query_legal as _notebook_query_legal,
        notebook_list_tagged as _notebook_list_tagged,
        notebook_create_legal as _notebook_create_legal,
        notebook_add_source as _notebook_add_source,
        notebook_research_legal as _notebook_research_legal,
        notebook_research_existing as _notebook_research_existing,
        notebook_status as _notebook_status,
        notebook_describe_cuaderno as _notebook_describe_cuaderno,
        notebook_get_source_content as _notebook_get_source_content,
        notebook_describe_source as _notebook_describe_source,
        notebook_create_report as _notebook_create_report,
        notebook_add_drive as _notebook_add_drive,
        notebook_delete_cuaderno as _notebook_delete_cuaderno,
        notebook_delete_source as _notebook_delete_source,
        notebook_ingest_jurisprudencia as _notebook_ingest_jurisprudencia,
        notebook_linea_jurisprudencial as _notebook_linea_jurisprudencial,
        notebook_red_team_legal as _notebook_red_team_legal,
    )
    _NOTEBOOK_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ No se pudieron importar todas las herramientas de NotebookLM Legal.")
    _NOTEBOOK_AVAILABLE = False


def _notebook_unavailable_error():
    """Retorna error estándar cuando NotebookLM no está disponible."""
    return {"error": "Herramientas de NotebookLM Legal no disponibles. Verifica la instalación del módulo."}


@register_tool("notebook_query_legal")
async def handle_notebook_query_legal(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_query_legal(**args)


@register_tool("notebook_list_tagged")
async def handle_notebook_list_tagged(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_list_tagged(**args)


@register_tool("notebook_create_legal")
async def handle_notebook_create_legal(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_create_legal(**args)


@register_tool("notebook_add_source")
async def handle_notebook_add_source(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_add_source(**args)


@register_tool("notebook_research_legal")
async def handle_notebook_research_legal(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_research_legal(**args)


@register_tool("notebook_research_existing")
async def handle_notebook_research_existing(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_research_existing(**args)


@register_tool("notebook_status")
async def handle_notebook_status(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_status(**args)


@register_tool("notebook_describe_cuaderno")
async def handle_notebook_describe_cuaderno(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_describe_cuaderno(**args)


@register_tool("notebook_get_source_content")
async def handle_notebook_get_source_content(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_get_source_content(**args)


@register_tool("notebook_describe_source")
async def handle_notebook_describe_source(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_describe_source(**args)


@register_tool("notebook_create_report")
async def handle_notebook_create_report(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_create_report(**args)


@register_tool("notebook_add_drive")
async def handle_notebook_add_drive(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_add_drive(**args)


@register_tool("notebook_delete_cuaderno")
async def handle_notebook_delete_cuaderno(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_delete_cuaderno(**args)


@register_tool("notebook_delete_source")
async def handle_notebook_delete_source(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_delete_source(**args)


@register_tool("notebook_ingest_jurisprudencia")
async def handle_notebook_ingest_jurisprudencia(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_ingest_jurisprudencia(**args)


@register_tool("notebook_linea_jurisprudencial")
async def handle_notebook_linea_jurisprudencial(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_linea_jurisprudencial(**args)


@register_tool("notebook_red_team_legal")
async def handle_notebook_red_team_legal(args: dict, session: AsyncSession, username: str) -> dict:
    if not _NOTEBOOK_AVAILABLE:
        return _notebook_unavailable_error()
    return await _notebook_red_team_legal(**args)
