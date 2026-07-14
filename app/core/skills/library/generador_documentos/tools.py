"""
Herramientas del skill generador_documentos.

Proporciona generación avanzada de documentos legales con:
- Validación previa de variables
- Integración con cálculos laborales
- Previsualización de documentos
"""
import os
import logging
import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Importaciones seguras de dependencias internas
try:
    from app.core.config import settings
    PLANTILLAS_DIR = settings.PLANTILLAS_DIR
    OUTPUT_DIR = settings.OUTPUT_DIR
except ImportError:
    PLANTILLAS_DIR = "plantillas"
    OUTPUT_DIR = "output"

try:
    from app.core.tools.calculadora_liquidacion import calcular_liquidacion, LiquidacionInput
except ImportError:
    calcular_liquidacion = None
    LiquidacionInput = None


# --- SCHEMAS PYDANTIC ---

class GenerarDocumentoInput(BaseModel):
    """Input para generación de documentos legales desde plantilla."""
    plantilla_filename: str = Field(
        ..., 
        description="Nombre exacto del archivo plantilla (ej: 'contrato.docx', 'tutela.md')"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Variables JSON para inyectar en la plantilla (ej: {nombre_completo: 'Juan Pérez'})"
    )
    incluir_calculos_laborales: bool = Field(
        False, 
        description="Si es True, calcula automáticamente liquidación laboral e inyecta resultados"
    )

    @field_validator("plantilla_filename")
    @classmethod
    def validar_extension(cls, v: str) -> str:
        """Valida que la plantilla tenga extensión soportada."""
        extensiones_validas = ('.docx', '.md', '.txt')
        if not v.lower().endswith(extensiones_validas):
            raise ValueError(f"La plantilla debe tener extensión {extensiones_validas}")
        return v


class ValidarDocumentoInput(BaseModel):
    """Input para validación de conformidad legal de un documento."""
    documento_texto: str = Field(
        ..., 
        min_length=20, 
        description="Texto del documento a validar (mínimo 20 caracteres)"
    )
    tipo_documento: str = Field(
        ..., 
        description="Tipo de documento: tutela, contrato, poder, memorando, certificado"
    )


class PrevisualizarDocumentoInput(BaseModel):
    """Input para previsualización de documento con variables."""
    plantilla_filename: str = Field(
        ..., 
        description="Nombre del archivo plantilla a previsualizar"
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Variables a inyectar para la previsualización"
    )


# --- FUNCIONES DE HERRAMIENTAS ---

def generar_documento_legal(
    plantilla_filename: str,
    variables: dict = {},
    incluir_calculos_laborales: bool = False
) -> dict:
    """
    Genera un documento legal completo integrando cálculos laborales si aplica.
    
    Esta herramienta orquesta el flujo completo:
    1. Valida que la plantilla exista
    2. Si es laboral, calcula liquidación automáticamente  
    3. Genera el documento con las variables inyectadas
    4. Retorna la URL de descarga
    
    Returns:
        Dict con status, filename, download_url y message
    """
    import asyncio
    
    try:
        # 1. Verificar que la plantilla existe
        ruta_plantilla = os.path.join(PLANTILLAS_DIR, plantilla_filename)
        if not os.path.exists(ruta_plantilla):
            return {
                "error": f"Plantilla '{plantilla_filename}' no encontrada en el servidor.",
                "sugerencia": "Usa la herramienta list_templates para ver las plantillas disponibles."
            }
        
        # 2. Si se solicitan cálculos laborales, ejecutarlos
        if incluir_calculos_laborales and calcular_liquidacion:
            datos_laborales = {
                "salario_mensual": variables.get("salario_base_mensual") or variables.get("salario_mensual"),
                "fecha_ingreso": variables.get("fecha_ingreso"),
                "fecha_retiro": variables.get("fecha_retiro"),
                "auxilio_transporte": variables.get("auxilio_transporte", 0),
                "incluye_auxilio_en_base": False,
                "tipo_contrato": variables.get("tipo_contrato", "indefinido"),
                "causa_retiro": variables.get("causa_retiro", "renuncia"),
            }
            
            salario = datos_laborales.get("salario_mensual")
            fecha_ing = datos_laborales.get("fecha_ingreso")
            fecha_ret = datos_laborales.get("fecha_retiro")
            
            if salario and fecha_ing and fecha_ret:
                try:
                    # Determinar si incluye auxilio en base (salario <= 2 SMMLV 2026)
                    smmlv_2026 = 1_423_500  # SMMLV 2026 Colombia
                    if float(salario) <= (2 * smmlv_2026):
                        datos_laborales["incluye_auxilio_en_base"] = True
                    
                    datos_laborales["salario_mensual"] = float(salario)
                    datos_laborales["auxilio_transporte"] = float(datos_laborales.get("auxilio_transporte", 0))
                    
                    # Convertir fechas string a date
                    from datetime import datetime as dt
                    if isinstance(fecha_ing, str):
                        datos_laborales["fecha_ingreso"] = dt.strptime(fecha_ing, "%Y-%m-%d").date()
                    if isinstance(fecha_ret, str):
                        datos_laborales["fecha_retiro"] = dt.strptime(fecha_ret, "%Y-%m-%d").date()
                    
                    liquidacion_input = LiquidacionInput(**datos_laborales)
                    calculos = calcular_liquidacion(liquidacion_input)
                    
                    # Inyectar resultados en las variables del documento
                    variables.update({
                        "cesantias": f"${calculos['cesantias']:,.2f}",
                        "intereses_cesantias": f"${calculos['intereses_cesantias']:,.2f}",
                        "prima_servicios": f"${calculos['prima']:,.2f}",
                        "vacaciones": f"${calculos['vacaciones']:,.2f}",
                        "indemnizacion": f"${calculos['indemnizacion']:,.2f}" if calculos.get("indemnizacion") else "N/A",
                        "total_liquidacion": f"${calculos['total_prestaciones']:,.2f}",
                        "dias_trabajados": str(calculos['dias_trabajados']),
                    })
                    
                    logger.info(f"✅ Cálculos laborales inyectados: {calculos}")
                except Exception as e:
                    logger.warning(f"⚠️ Error en cálculos laborales (no crítico): {e}")
                    # No es crítico, continuamos sin los cálculos
        
        # 3. Delegar la generación real al servicio existente (internal_generate_document)
        # Como esta función es sincrónica y generate_document usa async,
        # retornamos los datos para que el execute_tool del router lo maneje
        # Alternativamente, delegamos al tool generate_document ya existente en ai.py
        
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(plantilla_filename)[0]
        # Sanitizar nombre
        base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        
        return {
            "status": "delegate_to_generate_document",
            "filename": plantilla_filename,
            "variables": variables,
            "custom_filename": f"{base_name}_{ts}",
            "message": f"Documento preparado para generación desde '{plantilla_filename}' con {len(variables)} variables."
        }
        
    except Exception as e:
        logger.error(f"Error en generar_documento_legal: {e}")
        return {"error": f"Error generando documento: {str(e)}"}


def validar_documento(documento_texto: str, tipo_documento: str) -> dict:
    """
    Valida que un documento cumpla con los requisitos legales básicos colombianos.
    
    Verifica la presencia de elementos legales clave según el tipo de documento.
    
    Returns:
        Dict con cumplimiento, problemas, porcentaje y recomendaciones
    """
    # Checklists de conformidad por tipo de documento colombiano
    checklists = {
        "tutela": {
            "elementos": ["hechos", "derecho", "pretensiones", "juez", "accionante", "accionado"],
            "normas": ["Artículo 86 Constitución", "Decreto 2591 de 1991"]
        },
        "contrato": {
            "elementos": ["partes", "objeto", "obligaciones", "plazo", "valor", "firma"],
            "normas": ["Código Civil Art. 1495", "Código de Comercio Art. 864"]
        },
        "poder": {
            "elementos": ["poderdante", "apoderado", "facultades", "identificación", "firma"],
            "normas": ["Código General del Proceso Art. 74"]
        },
        "memorando": {
            "elementos": ["destinatario", "asunto", "fecha", "cuerpo", "remitente"],
            "normas": []
        },
        "certificado": {
            "elementos": ["entidad", "certifica", "fecha", "firma", "cargo"],
            "normas": []
        },
        "derecho_peticion": {
            "elementos": ["destinatario", "hechos", "peticion", "fundamentos", "peticionario"],
            "normas": ["Artículo 23 Constitución", "Ley 1755 de 2015"]
        },
    }
    
    tipo_lower = tipo_documento.lower().replace(" ", "_")
    checklist_data = checklists.get(tipo_lower, {"elementos": [], "normas": []})
    checklist = checklist_data["elementos"]
    normas = checklist_data["normas"]
    
    if not checklist:
        return {
            "status": "warning",
            "message": f"No hay checklist predefinido para tipo '{tipo_documento}'. Se realizará análisis general.",
            "cumplimiento": {},
            "recomendaciones": ["Verificar con abogado especializado"]
        }
    
    # Validar presencia de elementos clave
    texto_lower = documento_texto.lower()
    cumplimiento = {}
    
    for elemento in checklist:
        # Buscar variaciones del elemento en el texto
        variaciones = [elemento, elemento.replace("_", " ")]
        encontrado = any(var in texto_lower for var in variaciones)
        cumplimiento[elemento] = encontrado
    
    problemas = [elem for elem, cumple in cumplimiento.items() if not cumple]
    total = len(checklist)
    aprobados = total - len(problemas)
    porcentaje = (aprobados / total * 100) if total > 0 else 100
    
    # Generar recomendaciones específicas
    recomendaciones = []
    if problemas:
        recomendaciones.append(f"Faltan {len(problemas)} elementos clave: {', '.join(problemas)}")
        recomendaciones.append("Revisar con abogado antes de presentar formalmente")
    else:
        recomendaciones.append("El documento parece contener todos los elementos requeridos")
    
    if normas:
        recomendaciones.append(f"Marco legal aplicable: {', '.join(normas)}")
    
    recomendaciones.append("IMPORTANTE: Este análisis es automatizado. Se recomienda revisión por profesional del derecho.")
    
    return {
        "status": "valid" if porcentaje >= 80 else "needs_review",
        "tipo_documento": tipo_documento,
        "cumplimiento": cumplimiento,
        "elementos_aprobados": aprobados,
        "elementos_total": total,
        "problemas_detectados": problemas,
        "porcentaje_conformidad": round(porcentaje, 2),
        "normas_aplicables": normas,
        "recomendaciones": recomendaciones
    }


def previsualizar_documento(plantilla_filename: str, variables: dict = {}) -> dict:
    """
    Muestra las variables requeridas de una plantilla y cuáles ya tienen valor.
    
    Returns:
        Dict con variables requeridas, proporcionadas y faltantes
    """
    try:
        ruta_plantilla = os.path.join(PLANTILLAS_DIR, plantilla_filename)
        if not os.path.exists(ruta_plantilla):
            return {"error": f"Plantilla '{plantilla_filename}' no encontrada."}
        
        # Obtener variables de la plantilla
        from app.services.template_manager import TemplateManager
        vars_requeridas = TemplateManager.get_template_variables(template_path=ruta_plantilla)
        
        # Clasificar variables
        proporcionadas = {v: variables.get(v, "") for v in vars_requeridas if v in variables}
        faltantes = [v for v in vars_requeridas if v not in variables]
        
        return {
            "plantilla": plantilla_filename,
            "variables_requeridas": vars_requeridas,
            "variables_proporcionadas": proporcionadas,
            "variables_faltantes": faltantes,
            "total_requeridas": len(vars_requeridas),
            "total_proporcionadas": len(proporcionadas),
            "total_faltantes": len(faltantes),
            "completado_pct": round(
                (len(proporcionadas) / len(vars_requeridas) * 100) if vars_requeridas else 100, 2
            ),
            "listo_para_generar": len(faltantes) == 0,
            "message": f"{'✅ Listo para generar' if len(faltantes) == 0 else f'⚠️ Faltan {len(faltantes)} variables: {faltantes}'}"
        }
    except Exception as e:
        logger.error(f"Error en previsualizar_documento: {e}")
        return {"error": f"Error previsualizando: {str(e)}"}


class VerificarIntegridadInput(BaseModel):
    """Input para verificación de integridad de un documento firmado."""
    documento_filename: str = Field(
        ...,
        description="Nombre del archivo en la carpeta output/ para verificar su integridad criptográfica y firma (ej: 'contrato.docx')"
    )


def verificar_integridad_documento(documento_filename: str) -> dict:
    """
    Verifica la integridad de un documento previamente generado en la carpeta output/
    comparando su hash actual con el registrado en su sello de firma electrónica.
    De conformidad con el Decreto 2364 de 2012 de Colombia.
    """
    try:
        file_path = os.path.join(OUTPUT_DIR, documento_filename)
        if not os.path.exists(file_path):
            return {
                "success": False,
                "status": "NO_ENCONTRADO",
                "message": f"El archivo '{documento_filename}' no se encuentra en el servidor. Asegúrese de que esté en la carpeta output/."
            }
            
        import hashlib
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        
        base_name, _ = os.path.splitext(documento_filename)
        firma_filename = f"{base_name}_firma.json"
        firma_path = os.path.join(OUTPUT_DIR, firma_filename)
        
        firma_metadata = None
        if os.path.exists(firma_path):
            import json
            try:
                with open(firma_path, "r", encoding="utf-8") as f:
                    firma_metadata = json.load(f)
            except Exception as e:
                logger.error(f"Error leyendo archivo de firma {firma_filename}: {e}")
                
        if firma_metadata:
            matched = (firma_metadata.get("sha256_hash") == file_hash)
            return {
                "success": True,
                "status": "INTEGRO" if matched else "MODIFICADO",
                "message": "El documento coincide exactamente con el sello de firma registrado y no ha sido alterado." if matched else "El documento ha sido alterado y no coincide con el hash original de su firma.",
                "hash_calculado": file_hash,
                "registro_firma": firma_metadata
            }
        else:
            return {
                "success": False,
                "status": "NO_REGISTRADO",
                "message": f"No se encontró ningún registro de firma electrónica o sello de integridad para '{documento_filename}' en el servidor. Su autenticidad no puede certificarse.",
                "hash_calculado": file_hash
            }
    except Exception as e:
        logger.error(f"Error en verificar_integridad_documento: {e}")
        return {"error": f"Error en verificación: {str(e)}"}


# --- EXPORTACIONES ESTÁNDAR PARA SKILL MANAGER ---

def get_tools_schema():
    """Retorna schemas de herramientas para Gemini Function Calling."""
    return [
        {
            "name": "generar_documento_legal",
            "description": "Genera un documento legal completo desde una plantilla con variables. Integra cálculos laborales automáticos si se solicita. Retorna URL de descarga.",
            "parameters": GenerarDocumentoInput.model_json_schema()
        },
        {
            "name": "validar_documento",
            "description": "Valida que un texto de documento legal cumpla con los requisitos básicos colombianos. Verifica presencia de elementos clave según el tipo de documento.",
            "parameters": ValidarDocumentoInput.model_json_schema()
        },
        {
            "name": "previsualizar_documento",
            "description": "Muestra qué variables requiere una plantilla, cuáles ya tienen valor y cuáles faltan. Útil para verificar antes de generar.",
            "parameters": PrevisualizarDocumentoInput.model_json_schema()
        },
        {
            "name": "verificar_integridad_documento",
            "description": "Verifica si un documento de la carpeta output/ ha sido modificado o alterado desde su firma electrónica. De conformidad con la Ley 527 de 1999.",
            "parameters": VerificarIntegridadInput.model_json_schema()
        }
    ]


def get_tools():
    """Retorna las funciones ejecutables correspondientes."""
    return [generar_documento_legal, validar_documento, previsualizar_documento, verificar_integridad_documento]
