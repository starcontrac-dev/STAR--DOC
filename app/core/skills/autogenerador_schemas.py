"""
Autogenerador automático de esquemas (JSON Schema) para herramientas (tools) de la API de Gemini.

Inspecciona las firmas de funciones de Python anotadas y autogenera
esquemas compatibles con Gemini Function Calling, evitando la duplicación manual de schemas.
"""

import inspect
import logging
from typing import Callable, Dict, Any, get_type_hints, Union

logger = logging.getLogger(__name__)

def resolver_tipo_real(py_type: Any) -> Any:
    """Desenvuelve tipos Union (como Optional[T]) para encontrar el tipo subyacente."""
    origin = getattr(py_type, "__origin__", None)
    if origin is Union:
        args = getattr(py_type, "__args__", [])
        # Filtrar NoneType de la Union (Optional[T] = Union[T, None])
        tipos_no_none = [arg for arg in args if arg is not type(None)]
        if tipos_no_none:
            return resolver_tipo_real(tipos_no_none[0])
    return py_type

def mapear_tipo_python_a_gemini(py_type: Any) -> str:
    """Mapea tipos de Python a tipos compatibles con Gemini JSON Schema."""
    tipo_real = resolver_tipo_real(py_type)
    origin = getattr(tipo_real, "__origin__", None)
    
    if tipo_real == int:
        return "INTEGER"
    elif tipo_real == float:
        return "NUMBER"
    elif tipo_real == bool:
        return "BOOLEAN"
    elif tipo_real == list or origin is list:
        return "ARRAY"
    elif tipo_real == dict or origin is dict:
        return "OBJECT"
    else:
        return "STRING"

def parsear_descripciones_parametros(docstring: str) -> Dict[str, str]:
    """
    Parseador heurístico simple de docstrings (Google/Sphinx/Simple)
    para extraer las descripciones de los parámetros.
    """
    descripciones = {}
    if not docstring:
        return descripciones
        
    lineas = docstring.split("\n")
    for linea in lineas:
        linea_limpia = linea.strip()
        
        # Formato Sphinx: :param nombre: descripcion
        if linea_limpia.startswith(":param "):
            partes = linea_limpia.split(":", 2)
            if len(partes) >= 3:
                param_part = partes[1].replace("param", "").strip()
                desc_part = partes[2].strip()
                descripciones[param_part] = desc_part
                
        # Formato Google o descriptivo simple: nombre: descripción
        elif ":" in linea_limpia and not linea_limpia.startswith("http"):
            partes = linea_limpia.split(":", 1)
            posible_nombre = partes[0].strip()
            # Los nombres de parámetros no contienen espacios
            if posible_nombre and " " not in posible_nombre and not posible_nombre.startswith("-"):
                descripciones[posible_nombre] = partes[1].strip()
                
    return descripciones

def generar_gemini_schema_de_funcion(func: Callable) -> Dict[str, Any]:
    """
    Inspecciona la firma de una función de Python y genera de forma automática
    el esquema JSON Schema compatible con Gemini Function Calling.
    
    Args:
        func: Función de Python anotada a inspeccionar.
        
    Returns:
        Dict: Esquema compatible con Gemini.
    """
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)
    docstring = inspect.getdoc(func) or ""
    
    # Parsear descripciones del docstring
    desc_params = parsear_descripciones_parametros(docstring)
    
    # Extraer descripción general de la función (primera sección del docstring)
    descripcion_general = docstring.split("\n\n")[0].strip() if docstring else f"Herramienta {func.__name__}"
    
    properties = {}
    required = []
    
    for param_name, param in signature.parameters.items():
        # Ignorar parámetros especiales de clase/contexto
        if param_name in ("self", "cls", "db", "session"):
            continue
            
        param_type = type_hints.get(param_name, str)
        tipo_gemini = mapear_tipo_python_a_gemini(param_type)
        
        # Obtener descripción del docstring o un fallback descriptivo
        desc = desc_params.get(param_name, f"Parámetro {param_name} de tipo {tipo_gemini}.")
        
        properties[param_name] = {
            "type": tipo_gemini,
            "description": desc
        }
        
        # Si el parámetro no tiene un valor por defecto, es obligatorio
        if param.default == inspect.Parameter.empty:
            required.append(param_name)
            
    schema = {
        "name": func.__name__,
        "description": descripcion_general,
        "parameters": {
            "type": "OBJECT",
            "properties": properties
        }
    }
    
    if required:
        schema["parameters"]["required"] = required
        
    return schema
