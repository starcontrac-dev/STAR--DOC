"""
Herramientas del Skill de Consulta de Expedientes Judiciales.

Provee la función `buscar_expediente_judicial` que el agente Gemini
puede invocar para consultar portales judiciales colombianos.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def buscar_expediente_judicial(
    numero_radicacion: str = None,
    nombre_parte: str = None,
    portal: str = "rama_judicial",
    sentencia: str = None
) -> dict:
    """
    Consulta expedientes judiciales en portales oficiales de Colombia.
    
    Args:
        numero_radicacion: Número de radicación del proceso (23 dígitos)
        nombre_parte: Nombre o razón social para buscar
        portal: Portal a consultar (rama_judicial, samai, corte_constitucional)
        sentencia: Número de sentencia (ej: T-123/2025)
    
    Returns:
        Dict con resultados del proceso o error descriptivo
    """
    try:
        from app.core.tools.buscador_expedientes import buscador_expedientes
        
        if numero_radicacion:
            if portal == "samai":
                return await buscador_expedientes.consultar_samai(numero_radicacion)
            return await buscador_expedientes.consultar_por_radicacion(numero_radicacion)
        elif nombre_parte:
            return await buscador_expedientes.consultar_por_nombre(nombre_parte)
        elif sentencia:
            return await buscador_expedientes.consultar_sentencia_cc(sentencia)
        else:
            return {
                "error": "Debes proporcionar al menos uno de: numero_radicacion, nombre_parte o sentencia.",
                "ejemplo_radicacion": "11001-31-03-027-2024-00123-00",
                "ejemplo_sentencia": "T-760/2008",
                "portales_disponibles": ["rama_judicial", "samai", "corte_constitucional"]
            }
    except Exception as e:
        error_msg = str(e) or repr(e)
        logger.error(f"Error en buscar_expediente_judicial: {error_msg}")
        return {"error": f"Error consultando expediente: {error_msg}"}


def get_tools_schema():
    """Retorna el schema de herramientas para Gemini Function Calling."""
    return [{
        "name": "buscar_expediente_judicial",
        "description": "Consulta expedientes judiciales en portales oficiales de Colombia (Rama Judicial, SAMAI, Corte Constitucional). Usa Playwright para navegar portales con JavaScript. Soporta búsqueda por radicación (23 dígitos), nombre/razón social, o número de sentencia.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "numero_radicacion": {
                    "type": "STRING",
                    "description": "Número de radicación del proceso (formato: 11001-31-03-027-2024-00123-00)"
                },
                "nombre_parte": {
                    "type": "STRING",
                    "description": "Nombre completo o razón social de una de las partes del proceso"
                },
                "portal": {
                    "type": "STRING",
                    "description": "Portal judicial a consultar: 'rama_judicial' (por defecto), 'samai' (Consejo de Estado), 'corte_constitucional'"
                },
                "sentencia": {
                    "type": "STRING",
                    "description": "Número de sentencia de la Corte Constitucional (ej: T-123/2025, C-456/2024)"
                }
            }
        }
    }]


def get_tools():
    """Retorna las funciones ejecutables del skill."""
    return [buscar_expediente_judicial]
