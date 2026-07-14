"""
Herramientas (tools) v2.0 del skill NotebookLM Legal para STAR-DOC.

Mejoras v2.0:
- Decorador @require_service (elimina verificación repetitiva)
- 7 herramientas (antes 4): query, list, create, add_source, research, status, note
- Schemas Pydantic sincronizados con SKILL.md
- Validación de inputs real
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Importar el servicio singleton
try:
    from app.services.notebooklm_service import notebooklm_service
    notebooklm_service_error = None
except Exception as e:
    import traceback
    notebooklm_service = None
    notebooklm_service_error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    logger.warning(f"⚠️ NotebookLMService no disponible:\n{notebooklm_service_error}")


# ══════════════════════════════════════════════════════════
# DECORADOR — Elimina verificación repetitiva
# ══════════════════════════════════════════════════════════

def require_service(func):
    """Decorador que verifica la disponibilidad del servicio antes de ejecutar."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not notebooklm_service:
            return {"error": f"NotebookLMService no disponible. Error: {notebooklm_service_error}"}
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error en {func.__name__}: {e}")
            return {"error": str(e)}
    return wrapper


# ══════════════════════════════════════════════════════════
# SCHEMAS (Pydantic) — Para JSON Schemas de Gemini
# ══════════════════════════════════════════════════════════

class QueryLegalInput(BaseModel):
    class Config:
        extra = "allow"
    query: str = Field(..., description="Consulta jurídica (ej: 'requisitos tutela salud')")
    area_legal: Optional[str] = Field(
        None,
        description="Área: constitucional, administrativo, comercial, civil, tributario, laboral, penal, crypto"
    )
    category: str = Field(
        default="legal",
        description="Categoría de búsqueda: 'legal' (legislación) o 'juris' (jurisprudencia/sentencias)"
    )
    notebook_id: Optional[str] = Field(None, description="ID específico de un cuaderno.")
    source_format: Optional[str] = Field(
        None,
        description="Formato de citas: 'footnotes' (default), 'inline', 'json', 'expanded', 'none'"
    )


class ListTaggedInput(BaseModel):
    class Config:
        extra = "allow"
    tag: str = Field(
        ...,
        description="Etiqueta: #legal, #juris, #legal-constitucional, #juris-consejo_estado"
    )


class CreateLegalInput(BaseModel):
    class Config:
        extra = "allow"
    titulo: str = Field(..., description="Nombre descriptivo del cuaderno")
    area_legal: str = Field(..., description="Área: constitucional, administrativo, comercial, civil, tributario, laboral, penal, crypto")
    fuentes_urls: Optional[List[str]] = Field(None, description="URLs de fuentes iniciales (leyes, sentencias)")


class AddSourceInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno destino")
    url: Optional[str] = Field(None, description="URL de la fuente (ley, sentencia)")
    text: Optional[str] = Field(None, description="Texto para añadir como fuente")
    title: Optional[str] = Field(None, description="Título de la fuente de texto")


class ResearchLegalInput(BaseModel):
    class Config:
        extra = "allow"
    tema: str = Field(..., description="Tema jurídico a investigar")
    area_legal: str = Field(default="constitucional", description="Área del derecho")
    modo: str = Field(default="fast", description="Modo: 'fast' (~30s) o 'deep' (3-5 min)")


class ResearchInNotebookInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno EXISTENTE.")
    query: str = Field(..., description="Término de investigación a buscar.")
    modo: str = Field(default="fast", description="Modo: 'fast' (~30s) o 'deep' (3-5 min)")


class StatusInput(BaseModel):
    class Config:
        extra = "allow"
    check_connectivity: bool = Field(
        default=False,
        description="Si es True, verifica conectividad con el MCP (tarda ~10s). Si es False, solo estado local."
    )


class DescribeNotebookInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno a describir")


class GetSourceContentInput(BaseModel):
    class Config:
        extra = "allow"
    source_id: str = Field(..., description="ID de la fuente a la que se le extraerá el texto crudo")


class DescribeSourceInput(BaseModel):
    class Config:
        extra = "allow"
    source_id: str = Field(..., description="ID de la fuente a resumir")


class CreateReportInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno")
    source_ids: Optional[List[str]] = Field(None, description="Lista opcional de IDs de fuente a incluir")
    report_format: str = Field("Briefing Doc", description="Formato: 'Briefing Doc', 'Study Guide', 'Blog Post', 'Create Your Own'")
    custom_prompt: str = Field("", description="Prompt personalizado obligatorio para 'Create Your Own'")
    language: str = Field("es", description="Código del idioma de salida (es, en, etc.)")


class AddDriveSourceInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno destino")
    document_id: str = Field(..., description="ID del documento en Google Drive")
    title: str = Field(..., description="Título o nombre del archivo en Drive")
    doc_type: str = Field("doc", description="Tipo: doc, slides, sheets, pdf")


class DeleteNotebookInput(BaseModel):
    class Config:
        extra = "allow"
    notebook_id: str = Field(..., description="ID del cuaderno a eliminar")
    confirm: bool = Field(True, description="Confirmar eliminación permanente (debe ser True)")


class DeleteSourceInput(BaseModel):
    class Config:
        extra = "allow"
    source_id: str = Field(..., description="ID de la fuente a eliminar")
    confirm: bool = Field(True, description="Confirmar eliminación permanente (debe ser True)")


class IngestJurisprudenciaInput(BaseModel):
    class Config:
        extra = "allow"
    referencia: str = Field(..., description="Referencia de la sentencia o norma (ej: 'T-760/2008', 'Ley 1258 de 2008')")
    area_legal: str = Field("constitucional", description="Área: constitucional, administrativo, comercial, civil, tributario, laboral, penal, crypto")
    notebook_id: Optional[str] = Field(None, description="ID del cuaderno existente. Si es None, crea uno nuevo.")
    deep_research: bool = Field(False, description="Si es True, lanza una investigación web profunda en segundo plano.")
    max_sources: int = Field(5, description="Número máximo de fuentes a ingestar automáticamente (1 a 10)")


class LineaJurisprudencialInput(BaseModel):
    class Config:
        extra = "allow"
    tema: str = Field(..., description="Problema jurídico o tema a analizar")
    notebook_id: Optional[str] = Field(None, description="ID del cuaderno a analizar. Si es None, busca en la categoría de jurisprudencia.")
    corte: str = Field("todas", description="Filtrar por corte: 'corte_constitucional', 'corte_suprema', 'consejo_estado', 'todas'")
    generar_reporte: bool = Field(True, description="Si es True, genera un informe formal en PDF/Docx en el cuaderno.")


class RedTeamLegalInput(BaseModel):
    class Config:
        extra = "allow"
    texto: Optional[str] = Field(None, description="Texto del escrito jurídico a auditar.")
    document_id: Optional[int] = Field(None, description="ID de un documento guardado en la Bóveda RAG del usuario.")
    file_path: Optional[str] = Field(None, description="Ruta a un archivo local con el escrito jurídico.")
    nivel_profundidad: str = Field("standard", description="Nivel de análisis: 'rapido' (solo vigencia), 'standard' (vigencia + debilidades), 'exhaustivo' (todo + sugerencias)")
    area_legal: str = Field("constitucional", description="Área del derecho aplicable al escrito.")

# ══════════════════════════════════════════════════════════
# FUNCIONES DE HERRAMIENTAS
# ══════════════════════════════════════════════════════════

@require_service
async def notebook_query_legal(
    query: str,
    area_legal: str = None,
    category: str = "legal",
    notebook_id: str = None,
    source_format: str = None
) -> dict:
    """
    Consulta la base de conocimiento jurídico fundamentada.
    Retorna respuestas con cero alucinaciones y citas verificables.
    """
    return await notebooklm_service.query_legal(
        query=query, area_legal=area_legal,
        category=category,
        notebook_id=notebook_id,
        source_format=source_format
    )


@require_service
async def notebook_list_tagged(tag: str = "#legal") -> dict:
    """Lista cuadernos jurídicos (#legal) o de jurisprudencia (#juris)."""
    result = await notebooklm_service.search_by_tag(tag)
    status = notebooklm_service.get_status()
    if isinstance(result, dict):
        result["service_status"] = {
            "version": status.get("version", "2.0"),
            "cached_notebooks": status["cached_notebooks"],
            "available_tags": status["available_tags"],
            "circuit_breaker": status.get("circuit_breaker", "unknown"),
            "active_sessions": status.get("active_sessions", 0)
        }
    return result


@require_service
async def notebook_create_legal(
    titulo: str,
    area_legal: str,
    fuentes_urls: list = None
) -> dict:
    """
    Crea un cuaderno jurídico con etiqueta de área y fuentes iniciales opcionales.
    """
    return await notebooklm_service.create_legal_notebook(
        titulo=titulo, area_legal=area_legal, fuentes_urls=fuentes_urls
    )


@require_service
async def notebook_add_source(
    notebook_id: str,
    url: str = None,
    text: str = None,
    title: str = None
) -> dict:
    """Añade una fuente (URL o texto) a un cuaderno existente."""
    if url:
        return await notebooklm_service.add_url_source(notebook_id, url)
    elif text and title:
        return await notebooklm_service.add_text_source(notebook_id, text, title)
    else:
        return {"error": "Debes proporcionar 'url' o 'text' con 'title'."}


@require_service
async def notebook_research_legal(
    tema: str,
    area_legal: str = "constitucional",
    modo: str = "fast"
) -> dict:
    """
    Inicia investigación web sobre jurisprudencia o legislación.
    Crea un cuaderno nuevo con los resultados encontrados.
    """
    return await notebooklm_service.research_legal(
        tema=tema, area_legal=area_legal, modo=modo
    )


@require_service
async def notebook_research_existing(
    notebook_id: str,
    query: str,
    modo: str = "fast"
) -> dict:
    """Inicia investigación web vinculada a un cuaderno existente."""
    return await notebooklm_service.start_research(
        notebook_id=notebook_id, query=query, source="web", mode=modo
    )


@require_service
async def notebook_status(check_connectivity: bool = False) -> dict:
    """
    Verifica el estado del servicio NotebookLM.
    Con check_connectivity=True hace un health check completo (~10s).
    """
    if check_connectivity:
        return await notebooklm_service.check_health()
    else:
        return notebooklm_service.get_status()


@require_service
async def notebook_describe_cuaderno(notebook_id: str) -> dict:
    """Obtiene resumen de IA y temas del cuaderno."""
    return await notebooklm_service.describe_notebook(notebook_id)


@require_service
async def notebook_get_source_content(source_id: str) -> dict:
    """Obtiene el contenido de texto crudo de una fuente."""
    return await notebooklm_service.get_source_content(source_id)


@require_service
async def notebook_describe_source(source_id: str) -> dict:
    """Obtiene un resumen generado por IA de la fuente."""
    return await notebooklm_service.describe_source(source_id)


@require_service
async def notebook_create_report(
    notebook_id: str,
    source_ids: list = None,
    report_format: str = "Briefing Doc",
    custom_prompt: str = "",
    language: str = "es"
) -> dict:
    """Genera un informe formal en base al cuaderno."""
    return await notebooklm_service.create_report(
        notebook_id=notebook_id,
        source_ids=source_ids,
        report_format=report_format,
        custom_prompt=custom_prompt,
        language=language
    )


@require_service
async def notebook_add_drive(
    notebook_id: str,
    document_id: str,
    title: str,
    doc_type: str = "doc"
) -> dict:
    """Añade un documento de Google Drive como fuente al cuaderno."""
    return await notebooklm_service.add_drive_source(
        notebook_id=notebook_id,
        document_id=document_id,
        title=title,
        doc_type=doc_type
    )


@require_service
async def notebook_delete_cuaderno(notebook_id: str, confirm: bool = True) -> dict:
    """Elimina permanentemente un cuaderno."""
    return await notebooklm_service.delete_notebook(notebook_id, confirm)


@require_service
async def notebook_delete_source(source_id: str, confirm: bool = True) -> dict:
    """Elimina permanentemente una fuente."""
    return await notebooklm_service.delete_source(source_id, confirm)


@require_service
async def notebook_ingest_jurisprudencia(
    referencia: str,
    area_legal: str = "constitucional",
    notebook_id: str = None,
    deep_research: bool = False,
    max_sources: int = 5
) -> dict:
    """Ingesta jurisprudencia colombiana de manera automatizada."""
    return await notebooklm_service.ingest_jurisprudencia(
        referencia=referencia,
        area_legal=area_legal,
        notebook_id=notebook_id,
        deep_research=deep_research,
        max_sources=max_sources
    )


@require_service
async def notebook_linea_jurisprudencial(
    tema: str,
    notebook_id: str = None,
    corte: str = "todas",
    generar_reporte: bool = True
) -> dict:
    """Construye una línea jurisprudencial a partir de un tema jurídico."""
    return await notebooklm_service.build_linea_jurisprudencial(
        tema=tema,
        notebook_id=notebook_id,
        corte=corte,
        generar_reporte=generar_reporte
    )


@require_service
async def notebook_red_team_legal(
    texto: str = None,
    document_id: int = None,
    file_path: str = None,
    nivel_profundidad: str = "standard",
    area_legal: str = "constitucional"
) -> dict:
    """Audita de forma adversarial un escrito jurídico colombiano."""
    return await notebooklm_service.red_team_legal(
        texto=texto,
        document_id=document_id,
        file_path=file_path,
        nivel_profundidad=nivel_profundidad,
        area_legal=area_legal
    )

# ══════════════════════════════════════════════════════════
# REGISTROS PARA EL SKILL MANAGER
# ══════════════════════════════════════════════════════════

def get_tools_schema():
    """Retorna los schemas de las herramientas para Gemini Function Calling."""
    return [
        {
            "name": "notebook_query_legal",
            "description": (
                "Consulta la base de conocimiento en NotebookLM. "
                "Retorna respuestas FUNDAMENTADAS con citas y cero alucinaciones. "
                "Úsalo para verificar leyes o jurisprudencia específica."
            ),
            "parameters": QueryLegalInput.model_json_schema()
        },
        {
            "name": "notebook_list_tagged",
            "description": (
                "Lista los cuadernos disponibles filtrados por etiqueta (#legal, #juris). "
                "Descubre qué bases de conocimiento tiene el usuario."
            ),
            "parameters": ListTaggedInput.model_json_schema()
        },
        {
            "name": "notebook_create_legal",
            "description": (
                "Crea un cuaderno jurídico con etiqueta de área y fuentes iniciales. "
                "Úsalo cuando el usuario necesite una nueva base de conocimiento."
            ),
            "parameters": CreateLegalInput.model_json_schema()
        },
        {
            "name": "notebook_add_source",
            "description": (
                "Añade una fuente (URL o texto) a un cuaderno existente. "
                "IMPORTANTE: Primero lista cuadernos con notebook_list_tagged."
            ),
            "parameters": AddSourceInput.model_json_schema()
        },
        {
            "name": "notebook_research_legal",
            "description": (
                "Inicia investigación web sobre jurisprudencia o leyes. "
                "Crea un cuaderno nuevo y busca fuentes automáticamente."
            ),
            "parameters": ResearchLegalInput.model_json_schema()
        },
        {
            "name": "notebook_research_existing",
            "description": (
                "Investiga en la web y enlaza fuentes a un cuaderno EXISTENTE. "
                "Úsalo para expandir la base de un cuaderno de derecho."
            ),
            "parameters": ResearchInNotebookInput.model_json_schema()
        },
        {
            "name": "notebook_status",
            "description": (
                "Verifica el estado del servicio NotebookLM: conectividad, "
                "autenticación, cuadernos cacheados y métricas."
            ),
            "parameters": StatusInput.model_json_schema()
        },
        {
            "name": "notebook_describe_cuaderno",
            "description": (
                "Obtiene la ficha técnica de un cuaderno: resumen generado por IA "
                "y temas/conceptos sugeridos para guiar la consulta."
            ),
            "parameters": DescribeNotebookInput.model_json_schema()
        },
        {
            "name": "notebook_get_source_content",
            "description": (
                "Obtiene el texto original sin procesar por IA de una fuente. "
                "Ideal para extraer leyes, contratos o sentencias indexadas."
            ),
            "parameters": GetSourceContentInput.model_json_schema()
        },
        {
            "name": "notebook_describe_source",
            "description": (
                "Obtiene un resumen estructurado y palabras clave de una fuente "
                "individual (ley o sentencia)."
            ),
            "parameters": DescribeSourceInput.model_json_schema()
        },
        {
            "name": "notebook_create_report",
            "description": (
                "Genera un informe estructurado formal (memorial de tutela, study guide, etc.) "
                "a partir del cuaderno. Soporta formato 'Create Your Own' con prompt personalizado."
            ),
            "parameters": CreateReportInput.model_json_schema()
        },
        {
            "name": "notebook_add_drive",
            "description": (
                "Agrega un documento de Google Drive (Google Doc, Google Sheet, PDF) como "
                "fuente en un cuaderno de NotebookLM."
            ),
            "parameters": AddDriveSourceInput.model_json_schema()
        },
        {
            "name": "notebook_delete_cuaderno",
            "description": (
                "Elimina permanentemente un cuaderno completo del usuario. Esta acción es irreversible."
            ),
            "parameters": DeleteNotebookInput.model_json_schema()
        },
        {
            "name": "notebook_delete_source",
            "description": (
                "Elimina permanentemente una fuente individual de un cuaderno. Esta acción es irreversible."
            ),
            "parameters": DeleteSourceInput.model_json_schema()
        },
        {
            "name": "notebook_ingest_jurisprudencia",
            "description": (
                "Ingesta jurisprudencia colombiana de manera automática. Busca por radicado o "
                "ley en portales oficiales, prioriza dominios .gov.co e indexa en el cuaderno."
            ),
            "parameters": IngestJurisprudenciaInput.model_json_schema()
        },
        {
            "name": "notebook_linea_jurisprudencial",
            "description": (
                "Construye una línea jurisprudencial (precedente judicial colombiano) a partir "
                "de un tema, determinando la sentencia hito, ratio decidendi y estado actual."
            ),
            "parameters": LineaJurisprudencialInput.model_json_schema()
        },
        {
            "name": "notebook_red_team_legal",
            "description": (
                "Realiza una auditoría adversarial (Red Team) a un escrito jurídico colombiano. "
                "Detecta vigencia de citas, vacíos argumentativos y genera contraargumentos de la contraparte."
            ),
            "parameters": RedTeamLegalInput.model_json_schema()
        }
    ]


def get_tools():
    """Retorna las funciones ejecutables para el despacho dinámico."""
    return [
        notebook_query_legal,
        notebook_list_tagged,
        notebook_create_legal,
        notebook_add_source,
        notebook_research_legal,
        notebook_research_existing,
        notebook_status,
        notebook_describe_cuaderno,
        notebook_get_source_content,
        notebook_describe_source,
        notebook_create_report,
        notebook_add_drive,
        notebook_delete_cuaderno,
        notebook_delete_source,
        notebook_ingest_jurisprudencia,
        notebook_linea_jurisprudencial,
        notebook_red_team_legal,
    ]

