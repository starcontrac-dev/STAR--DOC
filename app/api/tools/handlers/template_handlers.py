"""
Handlers de herramientas de plantillas legales.

Herramientas:
- list_templates: Lista todas las plantillas disponibles
- get_template_variables: Obtiene las variables de una plantilla
- generate_document: Genera un documento a partir de una plantilla
- read_template_content: Lee el contenido de una plantilla
"""

import os
import logging
import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import register_tool
from app.core.config import settings
from app.services.template_manager import TemplateManager
from app.services.document_service import internal_generate_document
from app.services.files import extract_text_from_bytes
from app.core.utils import sanitize_filename

logger = logging.getLogger(__name__)

# Alias local para funciones de TemplateManager usadas en herramientas
get_template_variables_fn = TemplateManager.get_template_variables


@register_tool("list_templates")
async def handle_list_templates(args: dict, session: AsyncSession, username: str) -> dict:
    """Lista todas las plantillas de documentos legales disponibles."""
    try:
        all_templates = await TemplateManager.get_all_templates_combined(session)
        return {"templates": all_templates}
    except Exception as e:
        return {"error": str(e)}


@register_tool("get_template_variables")
async def handle_get_template_variables(args: dict, session: AsyncSession, username: str) -> dict:
    """Obtiene las variables (campos) de una plantilla específica."""
    filename = args.get("filename")
    if not filename:
        return {"error": "Falta filename"}
    
    path = os.path.join(settings.PLANTILLAS_DIR, filename)
    if not os.path.exists(path):
        return {"error": "Plantilla no encontrada"}
    
    try:
        # Esta función es sincrónica pero suficientemente rápida
        vars_list = get_template_variables_fn(template_path=path)
        return {"variables": vars_list}
    except Exception as e:
        return {"error": str(e)}


@register_tool("generate_document")
async def handle_generate_document(args: dict, session: AsyncSession, username: str) -> dict:
    """Genera el documento final cuando se tienen todas las variables llenas."""
    filename = args.get("filename")
    variables = args.get("variables", {})
    if not filename:
        return {"error": "Falta filename"}

    try:
        # Determinar un nombre amigable para el archivo
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Priorizar 'nombre_archivo' o 'title' de las variables
        base_name = (
            variables.get("nombre_archivo") 
            or variables.get("title") 
            or os.path.splitext(filename)[0]
        )
        # Limpiar el nombre base para que sea un nombre de archivo válido
        base_name = sanitize_filename(base_name)
        forced_filename = f"{base_name}_{ts}"

        out_name = await internal_generate_document(
            template_filename=filename,
            context=variables,
            output_format='docx',
            custom_filename=forced_filename
        )
        
        logger.info(f"Documento generado exitosamente: {out_name}")
        
        # Retornar JSON estructurado (más fácil de parsear para Gemini)
        return {
            "status": "success",
            "message": "Documento generado exitosamente",
            "filename": out_name,
            "download_url": f"/files/{out_name}"
        }
    except Exception as e:
        logger.error(f"Generation error: {e}")
        return {"error": f"Error generando documento: {str(e)}"}


@register_tool("read_template_content")
async def handle_read_template_content(args: dict, session: AsyncSession, username: str) -> dict:
    """Lee el contenido completo de una plantilla (Word o Markdown)."""
    filename = args.get("filename")
    if not filename:
        return {"error": "Falta filename"}

    path = os.path.join(settings.PLANTILLAS_DIR, filename)
    if not os.path.exists(path):
        return {"error": f"Plantilla '{filename}' no encontrada en el servidor."}

    try:
        with open(path, "rb") as f:
            content = f.read()

        text = await extract_text_from_bytes(content, filename)
        return {"filename": filename, "content": text}
    except Exception as e:
        return {"error": f"Error leyendo plantilla: {str(e)}"}
