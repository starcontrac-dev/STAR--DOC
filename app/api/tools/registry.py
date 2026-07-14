"""
Registro Central de Herramientas del Agente (Patrón Registry).

Proporciona un decorador `@register_tool` que cada módulo handler utiliza
para auto-registrar sus funciones ejecutables. El dispatcher consulta
este registro para despachar herramientas por nombre.

Ejemplo de uso en un handler:
    from app.api.tools.registry import register_tool

    @register_tool("mi_herramienta")
    async def handle_mi_herramienta(args: dict, session, username: str) -> dict:
        return {"resultado": "ok"}
"""

import logging
from typing import Dict, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

# Tipo de la función handler: recibe (args, session, username) y retorna dict
ToolHandler = Callable[..., Awaitable[Dict[str, Any]]]

# Registro global de herramientas: nombre -> función handler
_TOOL_REGISTRY: Dict[str, ToolHandler] = {}


def register_tool(name: str):
    """
    Decorador para registrar una herramienta en el registro global.
    
    Args:
        name: Nombre único de la herramienta (debe coincidir con el schema de Gemini).
    
    Raises:
        ValueError: Si ya existe una herramienta con el mismo nombre.
    """
    def decorator(func: ToolHandler) -> ToolHandler:
        if name in _TOOL_REGISTRY:
            logger.warning(f"⚠️ Herramienta '{name}' ya registrada. Sobreescribiendo.")
        _TOOL_REGISTRY[name] = func
        logger.debug(f"🔧 Herramienta registrada: {name}")
        return func
    return decorator


def get_tool(name: str):
    """
    Obtiene un handler registrado por nombre.
    
    Args:
        name: Nombre de la herramienta.
    
    Returns:
        El handler si existe, None si no.
    """
    return _TOOL_REGISTRY.get(name)


def get_all_tools() -> Dict[str, ToolHandler]:
    """Retorna una copia del registro completo de herramientas."""
    return dict(_TOOL_REGISTRY)


def list_registered_tools() -> list:
    """Retorna la lista de nombres de herramientas registradas."""
    return list(_TOOL_REGISTRY.keys())
