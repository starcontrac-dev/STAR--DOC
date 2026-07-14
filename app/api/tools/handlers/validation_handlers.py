"""
Handlers de herramientas de validación de datos legales.

Herramientas:
- validate_data: Valida datos contra esquemas Pydantic (ej: TutelaSchema)
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.api.tools.registry import register_tool
from app.schemas.legal_docs import (
    TutelaSchema,
    ContestacionTutelaSchema,
    RespuestaPeticionSchema,
    DerechoPeticionSchema
)

logger = logging.getLogger(__name__)


@register_tool("validate_data")
async def handle_validate_data(args: dict, session: AsyncSession, username: str) -> dict:
    """Valida los datos recolectados contra un esquema legal estricto."""
    schema_name = args.get("schema_name")
    data = args.get("data", {})
    
    schemas = {
        "TutelaSchema": TutelaSchema,
        "ContestacionTutelaSchema": ContestacionTutelaSchema,
        "RespuestaPeticionSchema": RespuestaPeticionSchema,
        "DerechoPeticionSchema": DerechoPeticionSchema
    }
    
    if schema_name not in schemas:
        return {"error": f"Esquema desconocido: {schema_name}"}
        
    schema_cls = schemas[schema_name]
    try:
        # Validación Pydantic
        schema_cls(**data)
        return {
            "status": "valid",
            "message": f"Datos Válidos para '{schema_name}'. Puedes proceder a generar el documento."
        }
    except ValidationError as e:
        # Formatear errores de validación de Pydantic de forma amigable
        error_details = []
        for err in e.errors():
            loc = " -> ".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "Error de validación")
            
            # Limpiar mensajes estándar en inglés para hacerlos amigables
            if "Field required" in msg:
                msg = "Este campo es requerido y no puede estar vacío."
            elif "value is not a valid" in msg:
                msg = "El valor proporcionado no tiene un formato válido."
            
            error_details.append(f"• Campo '{loc}': {msg}")
            
        return {
            "status": "invalid",
            "errors": error_details,
            "message": "Se encontraron errores de validación. Por favor, solicita o corrige estos campos con el usuario."
        }
    except Exception as e:
        logger.error(f"Error inesperado al validar {schema_name}: {e}")
        return {"status": "invalid", "errors": [str(e)]}

