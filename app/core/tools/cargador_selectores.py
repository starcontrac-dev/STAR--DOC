"""
Cargador dinámico de selectores para portales judiciales.

Permite cargar selectores desde un archivo JSON externo (data/selectores.json)
para realizar modificaciones en caliente sin reiniciar la aplicación,
con fallback automático a los selectores estáticos de selectores_portales.py.
"""

import os
import json
import time
import logging
from typing import Dict, Any

from app.core.tools.selectores_portales import SELECTORES, SELECTORES_JURISPRUDENCIA

logger = logging.getLogger(__name__)

# Configuración del archivo de selectores y caché
SELECTORES_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "selectores.json"
)

# Caché en memoria: { "data": dict, "timestamp": float }
_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0.0
}
CACHE_TTL_SECONDS = 300.0  # 5 minutos

def _cargar_selectores_json() -> Dict[str, Any]:
    """Carga los selectores desde el archivo JSON si el caché expiró."""
    ahora = time.time()
    if _cache["data"] is not None and (ahora - _cache["timestamp"] < CACHE_TTL_SECONDS):
        return _cache["data"]

    # Intentar cargar desde el archivo físico
    if os.path.exists(SELECTORES_JSON_PATH):
        try:
            with open(SELECTORES_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                _cache["data"] = data
                _cache["timestamp"] = ahora
                logger.info(f"🔄 Selectores cargados con éxito desde JSON ({SELECTORES_JSON_PATH})")
                return data
        except Exception as e:
            logger.error(f"❌ Error al leer o parsear selectores.json: {e}. Usando fallback estático.")
    else:
        logger.warning(f"⚠️ Archivo selectores.json no encontrado en {SELECTORES_JSON_PATH}. Usando fallback estático.")
        
    return {}

async def obtener_selectores_actualizados(portal_key: str, tipo: str = "selectores") -> Dict[str, Any]:
    """
    Obtiene los selectores actualizados para un portal específico.
    
    Args:
        portal_key: Identificador del portal (ej: 'rama_judicial', 'constitucional')
        tipo: 'selectores' para procesos ó 'selectores_jurisprudencia' para relatorías.
        
    Returns:
        Dict con los selectores del portal.
    """
    data = _cargar_selectores_json()
    
    # Resolver según el tipo solicitado
    if tipo == "selectores":
        selectores_dict = data.get("selectores", {})
        fallback_dict = SELECTORES
    else:
        selectores_dict = data.get("selectores_jurisprudencia", {})
        fallback_dict = SELECTORES_JURISPRUDENCIA
        
    # Intentar obtener del JSON
    portal_data = selectores_dict.get(portal_key)
    if portal_data:
        return portal_data
        
    # Fallback estático
    logger.debug(f"ℹ️ Usando selectores estáticos (fallback) para portal: {portal_key} ({tipo})")
    return fallback_dict.get(portal_key, {})
