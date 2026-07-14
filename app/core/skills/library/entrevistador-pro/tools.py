from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import re
from datetime import datetime

# Importaciones seguras de herramientas del core
try:
    from app.core.tools.calculadora_terminos import es_dia_habil, calcular_dias_habiles
except ImportError:
    es_dia_habil = None
    calcular_dias_habiles = None

# ==========================================
# 📋 SCHEMAS PYDANTIC PARA FUNCTION CALLING
# ==========================================

class CheckInterviewInput(BaseModel):
    template_type: str = Field(..., description="Nombre exacto del archivo de plantilla (ej: 'derecho_peticion.docx', 'tutela_salud.md')")
    collected_data: dict = Field(default_factory=dict, description="Diccionario con las variables de datos que ya se han recopilado hasta el momento")

class ValidarCampoInput(BaseModel):
    field_name: str = Field(..., description="Nombre técnico de la variable a validar")
    value: str = Field(..., description="El valor proporcionado por el usuario para su validación")
    field_type: str = Field(..., description="El tipo técnico del campo de acuerdo con la clasificación (ej: 'email', 'date', 'tel', 'number', 'text')")

class TerminoLegalInput(BaseModel):
    fecha_inicio: str = Field(..., description="Fecha inicial del hecho, notificación o radicación en formato YYYY-MM-DD")
    tipo_tramite: str = Field(..., description="Tipo de término procesal a calcular ('peticion_general', 'peticion_copias', 'peticion_consulta', 'impugnacion_tutela')")

class GuionEntrevistaInput(BaseModel):
    tipo_documento: str = Field(..., description="El tipo de trámite legal (ej: 'creacion_tutela', 'contestacion_tutela', 'creacion_peticion', 'respuesta_peticion', 'contrato')")
    contexto_caso: Optional[str] = Field(None, description="Contexto inicial del problema para refinar la entrevista")


# ==========================================
# 🛠️ FUNCIONES DE LA SKILL (HERRAMIENTAS)
# ==========================================

def check_interview_status(template_type: str, collected_data: dict = {}) -> dict:
    """
    Verifica qué variables de una plantilla están pendientes de recolectar analizando
    el archivo físico de la plantilla de forma dinámica en STAR-DOC.
    """
    try:
        from app.services.template_manager import TemplateManager
    except ImportError:
        return {"status": "error", "message": "No se pudo importar TemplateManager desde el core."}

    # 1. Resolver ruta física de la plantilla
    path = TemplateManager.resolve_template_path(template_type)
    if not path:
        return {
            "status": "pending_template",
            "message": f"La plantilla '{template_type}' no fue encontrada en el catálogo físico ni temporal.",
            "collected_fields_count": len(collected_data),
            "collected_fields": list(collected_data.keys())
        }

    # 2. Extraer variables reales declaradas (Jinja2 o DocxTemplate)
    variables = TemplateManager.get_template_variables(template_path=path)
    if not variables:
        return {
            "status": "empty_template",
            "message": "La plantilla no contiene variables declaradas o no se pudieron extraer.",
            "collected_fields_count": len(collected_data),
            "collected_fields": list(collected_data.keys())
        }

    # 3. Clasificar los campos para guiar al modelo sobre el tipo de input
    fields_classified = TemplateManager.classify_template_fields(variables)

    # 4. Normalizar datos recopilados por el usuario
    collected_keys = {k.strip(): v for k, v in collected_data.items() if v is not None and str(v).strip() != ""}
    
    pending_fields = []
    collected_fields = []
    
    for f in fields_classified:
        name = f["name"]
        if name in collected_keys:
            collected_fields.append({
                "name": name,
                "value": collected_keys[name],
                "label": f["label"]
            })
        else:
            pending_fields.append(f)

    # 5. Calcular porcentaje de progreso
    total_vars = len(variables)
    collected_count = len(collected_fields)
    progress = round((collected_count / total_vars) * 100, 2) if total_vars > 0 else 100.0

    return {
        "status": "complete" if len(pending_fields) == 0 else "collecting",
        "progress_percentage": progress,
        "template_name": template_type,
        "total_fields_count": total_vars,
        "collected_fields_count": collected_count,
        "pending_fields_count": len(pending_fields),
        "collected_fields": collected_fields,
        "pending_fields": pending_fields
    }


def validar_formato_campo(field_name: str, value: str, field_type: str) -> dict:
    """
    Valida en tiempo real si el valor provisto por el usuario cumple con las restricciones
    y formatos técnicos correctos para evitar errores tardíos en la generación del documento.
    """
    val_clean = str(value).strip()
    
    if field_type == "email":
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_regex, val_clean):
            return {
                "is_valid": False,
                "error_message": f"El correo electrónico '{value}' no tiene un formato válido (ej: usuario@dominio.com)."
            }
            
    elif field_type == "date":
        parsed_date = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed_date = datetime.strptime(val_clean, fmt)
                break
            except ValueError:
                continue
        if not parsed_date:
            return {
                "is_valid": False,
                "error_message": f"La fecha '{value}' no es válida. Usa el formato YYYY-MM-DD o DD/MM/YYYY."
            }
        
        now = datetime.now()
        if parsed_date.year > now.year + 5 or parsed_date.year < 1900:
            return {
                "is_valid": False,
                "error_message": "La fecha ingresada está fuera de un rango de calendario lógico (1900 - 2030)."
            }
            
    elif field_type == "tel":
        tel_clean = val_clean.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not tel_clean.replace("+", "").isdigit() or len(tel_clean) < 7:
            return {
                "is_valid": False,
                "error_message": f"El teléfono '{value}' no es válido. Debe contener solo números y el código de país si aplica (ej: +57 3001234567)."
            }
            
    elif field_type == "number":
        num_clean = val_clean.replace(",", "").replace("$", "").replace("'", "")
        try:
            float(num_clean)
        except ValueError:
            return {
                "is_valid": False,
                "error_message": f"El campo '{field_name}' requiere un valor numérico. El valor '{value}' no es un número válido."
            }
            
    return {
        "is_valid": True,
        "clean_value": val_clean
    }


def calcular_termino_legal_colombia(fecha_inicio: str, tipo_tramite: str) -> dict:
    """
    Calcula plazos legales en Colombia considerando días hábiles y festivos (Ley Emiliani),
    de acuerdo con la Ley 1755 de 2015 y el Decreto 2591 de 1991.
    """
    plazos = {
        "peticion_general": {"dias": 15, "sustento": "Art. 14 Ley 1755 de 2015 (15 días hábiles generales para peticiones)"},
        "peticion_copias": {"dias": 10, "sustento": "Art. 14 Ley 1755 de 2015 (10 días hábiles para solicitudes de información y copias)"},
        "peticion_consulta": {"dias": 30, "sustento": "Art. 14 Ley 1755 de 2015 (30 días hábiles para resolver consultas jurídicas)"},
        "impugnacion_tutela": {"dias": 3, "sustento": "Art. 31 Decreto 2591 de 1991 (3 días hábiles para presentar impugnación contra el fallo de tutela)"}
    }
    
    tipo_clean = tipo_tramite.lower().strip()
    if tipo_clean not in plazos:
        return {
            "status": "error",
            "message": f"Tipo de término legal '{tipo_tramite}' no reconocido. Opciones válidas: {list(plazos.keys())}"
        }
        
    dias_h = plazos[tipo_clean]["dias"]
    sustento = plazos[tipo_clean]["sustento"]
    
    if not calcular_dias_habiles:
        return {
            "status": "fallback",
            "dias_habiles_plazo": dias_h,
            "sustento_legal": sustento,
            "message": "Calculadora de festivos locales no disponible en el sistema. Se estima de manera aproximada."
        }
        
    try:
        # Calcular fecha límite real usando el módulo del core de STAR-DOC que analiza la ley colombiana y festivos
        result_fecha = calcular_dias_habiles(fecha_inicio, dias_h)
        fecha_resultado = result_fecha.get("fecha_resultado") if isinstance(result_fecha, dict) else result_fecha
        return {
            "status": "ok",
            "fecha_inicio": fecha_inicio,
            "fecha_limite": fecha_resultado,
            "dias_habiles_plazo": dias_h,
            "sustento_legal": sustento
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error al procesar el cálculo de términos hábiles: {e}"
        }


def generar_guion_entrevista_personalizado(tipo_documento: str, contexto_caso: Optional[str] = None) -> dict:
    """
    Genera un guion de entrevista estructurado. Primero intenta leer un guion personalizado
    en formato JSON desde la carpeta de guiones. Si no existe, realiza introspección
    dinámica de la plantilla correspondiente a través de TemplateManager como fallback.
    """
    import json
    import os
    
    tipo_doc_clean = tipo_documento.lower().strip()
    # Eliminar posibles extensiones si el usuario pasa el nombre del archivo
    nombre_base = tipo_doc_clean.replace(".docx", "").replace(".md", "")
    
    # Intentar resolver la ruta de la carpeta de guiones
    base_dir = os.path.dirname(os.path.abspath(__file__))
    guiones_dir = os.path.join(base_dir, "guiones")
    guion_path = os.path.join(guiones_dir, f"{nombre_base}.json")
    
    guion = None
    if os.path.exists(guion_path):
        try:
            with open(guion_path, "r", encoding="utf-8") as f:
                guion = json.load(f)
        except Exception as e:
            # Si hay un error al parsear el JSON, lo registramos pero continuamos para usar fallback
            pass
            
    # Fallback 1: Introspección dinámica de la plantilla física
    if not guion:
        try:
            from app.services.template_manager import TemplateManager
            # Intentar resolver la plantilla (usando el nombre recibido o con extensiones)
            path = TemplateManager.resolve_template_path(tipo_documento)
            if not path:
                # Probar con extensiones comunes
                for ext in [".docx", ".md"]:
                    path = TemplateManager.resolve_template_path(f"{nombre_base}{ext}")
                    if path:
                        break
            
            if path:
                variables = TemplateManager.get_template_variables(template_path=path)
                if variables:
                    fields = TemplateManager.classify_template_fields(variables)
                    
                    # Agrupar los campos en fases de máximo 3 preguntas
                    fases = []
                    campos_agrupados = [fields[i:i + 3] for i in range(0, len(fields), 3)]
                    
                    for idx, grupo in enumerate(campos_agrupados):
                        preguntas = []
                        for c_idx, campo in enumerate(grupo):
                            label = campo["label"]
                            f_type = campo["type"]
                            num_preg = c_idx + 1
                            
                            if f_type == "email":
                                q = f"{num_preg}. ¿Cuál es el correo electrónico o email para '{label}'?"
                            elif f_type == "date":
                                q = f"{num_preg}. ¿Qué fecha corresponde a '{label}'? (Por favor ingresa en formato YYYY-MM-DD)"
                            elif f_type == "tel":
                                q = f"{num_preg}. ¿Cuál es el número de teléfono o celular para '{label}'?"
                            elif f_type == "number":
                                if any(k in campo["name"].lower() for k in ["cc", "cedula", "nit", "identificacion"]):
                                    q = f"{num_preg}. ¿Cuál es el número de identificación o documento para '{label}'?"
                                else:
                                    q = f"{num_preg}. ¿Cuál es el valor numérico o monto en pesos ($) para '{label}'?"
                            elif f_type == "textarea":
                                q = f"{num_preg}. Por favor detalla la descripción o información para '{label}':"
                            else:
                                q = f"{num_preg}. Por favor ingresa el valor para el campo '{label}':"
                            preguntas.append(q)
                            
                        fases.append({
                            "nombre": f"Fase {idx + 1}: Recolección de Datos ({grupo[0]['label']} y otros)",
                            "preguntas": preguntas
                        })
                        
                    guion = {
                        "fases": fases,
                        "consejo_IA": "Pregunta de forma clara y con ejemplos de cada campo para evitar errores. Respeta la estructura de fases."
                    }
        except Exception as e:
            # Fallback en caso de que la introspección falle
            pass

    # Fallback 2: Guion genérico estático si todo lo demás falla
    if not guion:
        guion = {
            "fases": [
                {
                    "nombre": "Fase 1: Información General del Documento",
                    "preguntas": [
                        "1. ¿Quiénes son las partes que participan en este trámite (nombres completos, identificaciones)?",
                        "2. ¿Cuál es el objeto, situación de hecho o conflicto principal de este caso?"
                    ]
                },
                {
                    "nombre": "Fase 2: Condiciones Particulares y Plazos",
                    "preguntas": [
                        "1. ¿Cuál es el valor, monto o cuantía del asunto si aplica?",
                        "2. ¿Cuáles son los plazos, fechas clave o condiciones especiales que debemos establecer?"
                    ]
                }
            ],
            "consejo_IA": "Pregunta un máximo de 2 a 3 preguntas por turno de forma clara."
        }

    return {
        "tipo_documento": tipo_documento,
        "contexto_adicional": contexto_caso,
        "fases_guion": guion["fases"],
        "instruccion_entrevista": guion["consejo_IA"]
    }


# ==========================================
# 🔗 REGISTRO Y EXPORTACIÓN DE HERRAMIENTAS
# ==========================================

def get_tools_schema():
    """Retorna los schemas de herramientas disponibles para Gemini Function Calling."""
    return [
        {
            "name": "check_interview_status",
            "description": "Inspecciona la plantilla física de forma dinámica y verifica qué variables de datos hacen falta por recolectar.",
            "parameters": CheckInterviewInput.model_json_schema()
        },
        {
            "name": "validar_formato_campo",
            "description": "Valida en tiempo real si el valor provisto por el usuario cumple con las restricciones y formatos correctos (email, date, tel, number).",
            "parameters": ValidarCampoInput.model_json_schema()
        },
        {
            "name": "calcular_termino_legal_colombia",
            "description": "Calcula el plazo y fecha límite legal en Colombia de peticiones o tutelas considerando feriados y días hábiles.",
            "parameters": TerminoLegalInput.model_json_schema()
        },
        {
            "name": "generar_guion_entrevista_personalizado",
            "description": "Genera un guion de entrevista estructurado con las preguntas clave ordenadas por fases legales según el trámite.",
            "parameters": GuionEntrevistaInput.model_json_schema()
        }
    ]

def get_tools():
    """Retorna las funciones ejecutables correspondientes a los schemas."""
    return [
        check_interview_status,
        validar_formato_campo,
        calcular_termino_legal_colombia,
        generar_guion_entrevista_personalizado
    ]
