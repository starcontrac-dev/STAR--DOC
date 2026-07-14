"""
Despachador Central de Herramientas del Agente de IA.

Orquesta la ejecución de herramientas:
1. Busca en el ToolRegistry (herramientas registradas con @register_tool)
2. Si no se encuentra, busca en los skills dinámicos del SkillManager
3. Instrumenta cada llamada con métricas (FASE 8)

La función `execute_tool` es la interfaz pública principal.
"""

import time
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tools.registry import get_tool
from app.core.skills.manager import SkillManager
from app.services.document_service import internal_generate_document
from app.services.metrics_collector import metrics_collector

logger = logging.getLogger(__name__)

# Instancia del SkillManager para despacho dinámico
skill_manager = SkillManager()


async def execute_tool(name: str, args: dict, session: AsyncSession, username: str = "Anonimo") -> dict:
    """
    Punto de entrada principal para ejecutar cualquier herramienta por nombre.
    
    Instrumenta la ejecución con métricas de latencia y éxito/fallo (FASE 8).
    
    Args:
        name: Nombre de la herramienta a ejecutar
        args: Argumentos de la herramienta (dict de Gemini)
        session: Sesión async de la base de datos
        username: Nombre del usuario que ejecuta la herramienta
    
    Returns:
        dict: Resultado de la herramienta (siempre un dict JSON-serializable)
    """
    logger.info(f"Executing tool: {name} with args: {args} for user {username}")
    _tool_start = time.time()
    _tool_success = True
    _result = None
    try:
        _result = await _execute_tool_inner(name, args, session, username)
        if isinstance(_result, dict) and "error" in _result:
            _tool_success = False
        return _result
    except Exception as e:
        _tool_success = False
        _result = {"error": str(e)}
        raise
    finally:
        # FASE 8: Registrar métricas de la herramienta
        _duration_ms = (time.time() - _tool_start) * 1000
        metrics_collector.record_tool_call(
            tool_name=name,
            duration_ms=_duration_ms,
            success=_tool_success,
            params_summary=str(args)[:200]
        )
        metrics_collector.record_message()


async def _execute_tool_inner(name: str, args: dict, session: AsyncSession, username: str = "Anonimo") -> dict:
    """
    Lógica interna de despacho de herramientas (separada para instrumentación).
    
    1. Busca en el ToolRegistry (O(1) por diccionario)
    2. Si no existe, busca en skills dinámicos del SkillManager
    3. Si tampoco existe, retorna error
    """
    # --- PASO 1: Buscar en el registro de herramientas ---
    handler = get_tool(name)
    if handler:
        return await handler(args, session, username)
    
    # --- PASO 2: Herramienta de jurisprudencia especializada (skill legacy) ---
    if name == "buscar_jurisprudencia_especializada":
        try:
            from app.core.skills.library.jurisprudencia_pro.tools import (
                buscar_jurisprudencia_especializada as buscar_jurisprudencia_fn
            )
            return await buscar_jurisprudencia_fn(**args)
        except Exception as e:
            logger.error(f"Error en buscar_jurisprudencia_especializada: {e}")
            return {"error": f"Error en jurisprudencia: {str(e)}"}

    # --- PASO 3: Despacho dinámico de herramientas de Skills ---
    logger.info(f"🔎 Buscando herramienta '{name}' en skills dinámicos...")
    skill_id = getattr(skill_manager, "_tool_to_skill_map", {}).get(name)
    if skill_id:
        logger.info(f"✅ Herramienta '{name}' encontrada en skill '{skill_id}'")
        
        # 1. Consultar el rol del usuario en la base de datos de manera asíncrona
        from sqlmodel import select
        from app.models.user import User
        
        user_permissions = ["user"]
        try:
            query = select(User).where(User.username == username)
            db_user_result = await session.execute(query)
            db_user = db_user_result.scalar_one_or_none()
            if db_user:
                if db_user.role == "admin":
                    user_permissions = ["admin", "user"]
                else:
                    user_permissions = [db_user.role]
        except Exception as db_err:
            logger.error(f"Error al obtener rol de usuario '{username}' en base de datos: {db_err}")
            
        # 2. Canalizar la ejecución a través de skill_manager.execute_tool
        try:
            result = await skill_manager.execute_tool(skill_id, name, args, user_permissions, db=session)
        except PermissionError as perm_err:
            logger.warning(f"🚫 Permisos insuficientes para {username} al ejecutar {name}: {perm_err}")
            return {"error": f"Acceso denegado: {str(perm_err)}"}
        except Exception as exec_err:
            logger.error(f"Error ejecutando herramienta {name}: {exec_err}")
            return {"error": f"Error ejecutando herramienta: {str(exec_err)}"}
            
        # 3. Manejar delegación de generación de documentos
        if isinstance(result, dict) and result.get("status") == "delegate_to_generate_document":
            logger.info(f"📄 Delegando generación real de documento...")
            try:
                out_name = await internal_generate_document(
                    template_filename=result["filename"],
                    context=result.get("variables", {}),
                    output_format='docx',
                    custom_filename=result.get("custom_filename")
                )
                return {
                    "status": "success",
                    "message": "Documento generado exitosamente",
                    "filename": out_name,
                    "download_url": f"/files/{out_name}"
                }
            except Exception as gen_err:
                logger.error(f"Error en generación delegada: {gen_err}")
                return {"error": f"Error generando documento: {str(gen_err)}"}
        
        return result

    return {"error": f"Herramienta desconocida: {name}"}
