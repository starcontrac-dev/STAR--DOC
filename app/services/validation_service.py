import logging
from typing import Dict, Any, Type
from pydantic import BaseModel, ValidationError

from app.schemas.legal_docs import TutelaSchema, ContratoArrendamientoSchema, ContestacionTutelaSchema, RespuestaPeticionSchema, ContratoTrabajoSchema

logger = logging.getLogger(__name__)

# Mapeo de fragmentos del nombre del archivo a su respectivo esquema Pydantic
TEMPLATE_SCHEMA_MAP = {
    "contestacion_tutela": ContestacionTutelaSchema,
    "respuesta_peticion": RespuestaPeticionSchema,
    "accion_de_tutela": TutelaSchema,
    "tutela": TutelaSchema,
    "contrato_arrendamiento": ContratoArrendamientoSchema,
    "arrendamiento": ContratoArrendamientoSchema,
    "contrato_trabajo": ContratoTrabajoSchema,
    "laboral": ContratoTrabajoSchema,
}

def validate_document_context(template_filename: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Intenta validar el contexto provisto contra el esquema Pydantic correspondiente.
    Si se detecta un error de validación, lanza un ValueError explicando el problema.
    Devuelve un dict limpiado o el original si no hay validación estricta definida.
    """
    logger.info(f"Iniciando validación de contexto para la plantilla: {template_filename}")
    
    # 1. Identificar si existe un esquema para este template
    schema_class: Type[BaseModel] = None
    filename_lower = template_filename.lower()
    
    for key, model in TEMPLATE_SCHEMA_MAP.items():
        if key in filename_lower:
            schema_class = model
            break
            
    if not schema_class:
        logger.info(f"No se encontró un esquema Pydantic estricto para {template_filename}. Validacion Omitida.")
        return context

    # 2. Validar con Pydantic
    try:
        # Esto lanzará ValidationError si el contexto no cumple las reglas
        validated_data = schema_class(**context)
        logger.info(f"Validación exitosa usando {schema_class.__name__}")
        
        # Opcional: fusionar los datos validados con el contexto original por si
        # el docx usa mas campos adicionales ocultos que no esten en el schema.
        # Preferiblemente devolvemos el dict validado puro o actualizado.
        updated_context = context.copy()
        updated_context.update(validated_data.model_dump())
        return updated_context
        
    except ValidationError as e:
        logger.error(f"Fallo de validación Pydantic para {template_filename}:\n{e.json()}")
        # Simplificamos el error para devolverlo de manera limpia al requester
        error_msgs = []
        for err in e.errors():
            loc = err.get("loc", ())
            field = loc[0] if loc else "Documento (General)"
            msg = err.get("msg", "Error de valor")
            error_msgs.append(f"El campo '{field}' falló: {msg}")
            
        final_msg = " | ".join(error_msgs)
        raise ValueError(f"Datos inválidos para documento legal: {final_msg}")

