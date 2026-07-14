"""
Handler de herramienta de consulta de expedientes judiciales.

Herramientas:
- buscar_expediente_judicial: Consulta portales judiciales colombianos con Playwright
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("buscar_expediente_judicial")
async def handle_buscar_expediente_judicial(args: dict, session: AsyncSession, username: str) -> dict:
    """Consulta expedientes judiciales en portales oficiales de Colombia."""
    try:
        from app.core.skills.library.consulta_expedientes.tools import buscar_expediente_judicial
        return await buscar_expediente_judicial(**args)
    except Exception as e:
        logger.error(f"Error en buscar_expediente_judicial: {e}")
        return {"error": f"Error consultando expediente: {str(e)}"}
