import os
import json
import logging
import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from app.core.tools import buscador_jurisprudencia
except ImportError:
    buscador_jurisprudencia = None


# --- CLASIFICACIÓN DE PRECEDENTES COLOMBIANOS ---

def clasificar_peso_jurisprudencial(titulo: str, fuente: str) -> dict:
    """
    Analiza el título de la sentencia y determina su obligatoriedad legal en Colombia.
    De conformidad con el Artículo 230 de la Constitución y la jurisprudencia de las Altas Cortes.
    """
    titulo_upper = titulo.upper()
    
    if fuente == "constitucional":
        if "C-" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Constitucionalidad (C)",
                "obligatoriedad": "Erga Omnes (Efectos generales obligatorios)",
                "peso_vinculante": "Máximo (Fuerza de ley / Precedente Constitucional)",
                "fundamento_legal": "Art. 241 de la Constitución Política y Sentencia C-037 de 1996"
            }
        elif "SU-" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Unificación (SU)",
                "obligatoriedad": "Vinculante para Jueces y la Administración Pública",
                "peso_vinculante": "Máximo (Precedente vertical/horizontal obligatorio)",
                "fundamento_legal": "Decreto 2591 de 1991 y jurisprudencia unificada de la Corte"
            }
        elif "T-" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Tutela (T)",
                "obligatoriedad": "Efecto Inter Partes / Doctrina Constitucional Vinculante en su ratio",
                "peso_vinculante": "Medio-Alto (Criterio auxiliar obligatorio para casos análogos)",
                "fundamento_legal": "Art. 86 de la Constitución y Sentencia T-292 de 2006"
            }
            
    if fuente == "suprema":
        if "SL" in titulo_upper or "LABORAL" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Casación Laboral (SL)",
                "obligatoriedad": "Doctrina Probable para la Jurisdicción Ordinaria Laboral",
                "peso_vinculante": "Alto (Precedente de la Sala de Casación Laboral)",
                "fundamento_legal": "Art. 4 de la Ley 169 de 1896 y Art. 16 de la Ley 270 de 1996"
            }
        elif "SC" in titulo_upper or "CIVIL" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Casación Civil (SC)",
                "obligatoriedad": "Doctrina Probable para la Jurisdicción Ordinaria Civil",
                "peso_vinculante": "Alto (Precedente de la Sala de Casación Civil)",
                "fundamento_legal": "Art. 4 de la Ley 169 de 1896 y Art. 16 de la Ley 270 de 1996"
            }
        elif "SP" in titulo_upper or "PENAL" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Casación Penal (SP)",
                "obligatoriedad": "Doctrina Probable para la Jurisdicción Ordinaria Penal",
                "peso_vinculante": "Alto (Precedente de la Sala de Casación Penal)",
                "fundamento_legal": "Art. 4 de la Ley 169 de 1896"
            }
            
    if fuente == "consejo_estado":
        if "SUJ" in titulo_upper or "UNIFICACION" in titulo_upper:
            return {
                "tipo_sentencia": "Sentencia de Unificación Jurisprudencial (CE-SUJ)",
                "obligatoriedad": "Precedente Administrativo Obligatorio (Extensión de jurisprudencia)",
                "peso_vinculante": "Máximo (Contencioso Administrativo)",
                "fundamento_legal": "Artículos 10 y 102 de la Ley 1437 de 2011 (CPACA)"
            }
        else:
            return {
                "tipo_sentencia": "Sentencia de Sección / Subsección",
                "obligatoriedad": "Precedente Horizontal/Vertical Contencioso Administrativo",
                "peso_vinculante": "Medio-Alto",
                "fundamento_legal": "Art. 10 de la Ley 1437 de 2011"
            }
            
    return {
        "tipo_sentencia": "Fallo ordinario / Disposición normativa",
        "obligatoriedad": "Doctrina probable o fuente auxiliar",
        "peso_vinculante": "Medio-Bajo",
        "fundamento_legal": "Art. 230 de la Constitución Política (Criterio auxiliar)"
    }


# --- SCHEMAS DE INPUT PARA HERRAMIENTAS ---

class BuscadorInput(BaseModel):
    tema: str = Field(..., description="Tema jurídico a buscar o problema (ej. estabilidad laboral, despido)")
    fuente: str = Field(default="constitucional", description="Fuentes soportadas: constitucional, suprema, consejo_estado, sisjur, senado_leyes")
    max_resultados: int = Field(default=5, description="Número de resultados a extraer")
    tipo_proceso: str = Field(default=None, description="Opcional. Tipo de proceso (ej. Tutela, Casación)")
    palabras_clave: list[str] = Field(default=None, description="Opcional. Lista de palabras clave exactas a forzar en dorks.")
    anio_inicio: int = Field(default=2015, description="Año inicial para el rango de la búsqueda")
    anio_fin: int = Field(default=2026, description="Año final para el rango")


class FichaJurisprudencialInput(BaseModel):
    url_sentencia: Optional[str] = Field(None, description="URL de la sentencia en la relatoría oficial")
    texto_sentencia: Optional[str] = Field(None, description="Opcional. Texto de la sentencia si no se tiene la URL")


class LineaJurisprudencialInput(BaseModel):
    tema_linea: str = Field(..., description="Tema o problema jurídico para la línea (ej: estabilidad laboral reforzada prepensionados)")
    sentencias_titulos: list[str] = Field(..., description="Lista de títulos/radicados de las sentencias encontradas")


# --- FUNCIONES DE HERRAMIENTAS VINCULADAS ---

async def buscar_jurisprudencia_especializada(
    tema: str, 
    fuente: str = "constitucional", 
    tipo_proceso: str = None,
    palabras_clave: list[str] = None,
    anio_inicio: int = 2015,
    anio_fin: int = 2026,
    max_resultados: int = 5
) -> dict:
    """
    Busca jurisprudencia y clasifica jerárquicamente su obligatoriedad legal.
    """
    if not buscador_jurisprudencia:
        return {"error": "Herramienta buscador_jurisprudencia no disponible"}
    try:
        res = await buscador_jurisprudencia.buscar_jurisprudencia(
            tema=tema, fuente=fuente, tipo_proceso=tipo_proceso,
            palabras_clave=palabras_clave, anio_inicio=anio_inicio, 
            anio_fin=anio_fin, max_resultados=max_resultados
        )
        
        # Enriquecer los resultados con la obligatoriedad legal
        if res and "sentencias" in res:
            for s in res["sentencias"]:
                s["peso_jurisprudencial"] = clasificar_peso_jurisprudencial(s.get("titulo", ""), fuente)
                
        return res
    except Exception as e:
        logger.error(f"Error en buscar_jurisprudencia_especializada: {e}")
        return {"error": str(e)}


async def generar_ficha_jurisprudencial(
    url_sentencia: str = None, 
    texto_sentencia: str = None
) -> dict:
    """
    Analiza una sentencia real colombiana y extrae su ficha técnica estructurada
    (Corporación, Ponente, Radicado, Hechos, Problema Jurídico, Ratio Decidendi, Resuelve).
    """
    try:
        contenido_sentencia = ""
        
        if url_sentencia:
            if not buscador_jurisprudencia:
                return {"error": "Buscador de jurisprudencia no disponible para extraer URL"}
            # Extraer contenido de la sentencia usando Playwright
            res_ext = await buscador_jurisprudencia.buscador_legis.extraer_subregla(url_sentencia)
            if res_ext and len(res_ext) > 100:
                contenido_sentencia = res_ext
            else:
                contenido_sentencia = f"URL de consulta directa: {url_sentencia}"
        elif texto_sentencia:
            contenido_sentencia = texto_sentencia
        else:
            return {"error": "Debe proporcionar url_sentencia o texto_sentencia"}
            
        # Llamar a Gemini de manera asíncrona para estructurar la ficha
        from app.services.ai_service import ai_service
        
        prompt = (
            "Eres un Abogado Investigador Senior de Colombia. Tu tarea es analizar el siguiente fragmento "
            "o texto de una sentencia y estructurar una FICHA JURISPRUDENCIAL formal colombiana.\n\n"
            "El formato de salida DEBE ser un JSON estrictamente válido. IMPORTANTE: NO uses saltos de línea "
            "físicos reales dentro de los valores de las cadenas de texto del JSON; si necesitas un salto de línea, "
            "usa obligatoriamente el carácter de escape '\\n'.\n\n"
            "Estructura exacta requerida:\n"
            "{\n"
            '  "corporacion": "Nombre de la Corte (ej. Corte Constitucional)",\n'
            '  "radicado_sentencia": "Número de radicación o sentencia (ej. T-760/08)",\n'
            '  "magistrado_ponente": "Nombre del M.P.",\n'
            '  "hechos_relevantes": "Resumen de los hechos del caso",\n'
            '  "problema_juridico": "El problema jurídico de fondo que resuelve la Corte",\n'
            '  "ratio_decidendi": "La regla de derecho (Ratio Decidendi) que unifica o sienta el precedente",\n'
            '  "resuelve": "Sentido de la decisión (ej. Conceder el amparo)"\n'
            "}\n\n"
            f"Texto de la sentencia/datos a analizar:\n{contenido_sentencia[:8000]}"
        )
        
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ]
        }
        
        response = await ai_service.generate_content(payload=payload, timeout=60.0, add_grounding=False)
        
        candidates = response.get("candidates", [])
        if not candidates:
            return {"error": "No se obtuvo respuesta de la IA para estructurar la ficha"}
            
        part = candidates[0].get("content", {}).get("parts", [])[0]
        text_reply = part.get("text", "")
        
        ficha_data = limpiar_y_parsear_json_gemini(text_reply)
        return {
            "success": True,
            "ficha_jurisprudencial": ficha_data,
            "url_origen": url_sentencia
        }
    except Exception as e:
        logger.error(f"Error en generar_ficha_jurisprudencial: {e}")
        return {"error": f"Error estructurando ficha: {str(e)}"}


async def construir_linea_jurisprudencial(tema_linea: str, sentencias_titulos: list[str]) -> dict:
    """
    Organiza un conjunto de sentencias en una línea jurisprudencial estructurada temporal y conceptualmente.
    Identifica la sentencia fundadora, modificadoras y consolidadores (SU).
    """
    try:
        from app.services.ai_service import ai_service
        
        prompt = (
            "Eres un Abogado Investigador Senior experto en el método de Diego López Medina para construir "
            "líneas jurisprudenciales en Colombia. Tu tarea es tomar un tema y una lista de sentencias, "
            "y estructurar la línea jurisprudencial.\n\n"
            "El formato de salida DEBE ser un JSON estrictamente válido. IMPORTANTE: NO uses saltos de línea "
            "físicos reales dentro de los valores de las cadenas de texto del JSON; si necesitas un salto de línea "
            "en cualquier campo (incluyendo el timeline), usa obligatoriamente el carácter de escape '\\n'.\n\n"
            "Estructura exacta requerida:\n"
            "{\n"
            '  "tema_problema_juridico": "El problema jurídico abstracto de la línea",\n'
            '  "sentencia_hito_fundadora": "Identifica de la lista cuál o cuáles serían las fundadoras de la línea y por qué",\n'
            '  "sentencias_consolidacion_unificacion": "Identifica sentencias SU, C o SUJ que consoliden la regla",\n'
            '  "sentencias_modificadoras_viraje": "Identifica sentencias de cambio de precedente si las hay",\n'
            '  "regla_jurisprudencial_vigente": "La regla de derecho vigente al día de hoy para este problema",\n'
            '  "mermaid_timeline": "Código de diagrama Mermaid timeline que grafique la línea de forma temporal (ej: section 2015\\n  Sentencia T-123 : Funda regla\\n section 2024\\n  Sentencia SU-234 : Unifica criterio)"\n'
            "}\n\n"
            f"Tema de la Línea: {tema_linea}\n"
            f"Sentencias a Organizar: {', '.join(sentencias_titulos)}"
        )
        
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ]
        }
        
        response = await ai_service.generate_content(payload=payload, timeout=60.0, add_grounding=False)
        
        candidates = response.get("candidates", [])
        if not candidates:
            return {"error": "No se obtuvo respuesta de la IA para construir la línea"}
            
        part = candidates[0].get("content", {}).get("parts", [])[0]
        text_reply = part.get("text", "")
        
        linea_data = limpiar_y_parsear_json_gemini(text_reply)
        return {
            "success": True,
            "linea_jurisprudencial": linea_data
        }
    except Exception as e:
        logger.error(f"Error en construir_linea_jurisprudencial: {e}")
        return {"error": f"Error construyendo la línea: {str(e)}"}


def limpiar_y_parsear_json_gemini(text: str) -> dict:
    """
    Limpia y parsea de forma segura respuestas JSON de LLMs,
    manejando bloques de código markdown, comillas y saltos de línea físicos.
    """
    import re
    clean_json = text.strip()
    
    # 1. Eliminar bloques de código markdown
    if clean_json.startswith("```json"):
        clean_json = clean_json[7:]
    elif clean_json.startswith("```"):
        clean_json = clean_json[3:]
    if clean_json.endswith("```"):
        clean_json = clean_json[:-3]
    clean_json = clean_json.strip()
    
    # 2. Heurística de reparación: Reemplazar saltos de línea reales dentro de valores de strings
    try:
        return json.loads(clean_json)
    except json.JSONDecodeError as je:
        logger.warning(f"⚠️ Error inicial de JSON, intentando reparación defensiva: {je}")
        try:
            # Reemplaza saltos de línea físicos en valores de cadenas con '\\n'
            reparado = re.sub(
                r'":\s*"([^"]*?)"', 
                lambda m: '": "' + m.group(1).replace('\n', '\\n').replace('\r', '') + '"', 
                clean_json, 
                flags=re.DOTALL
            )
            return json.loads(reparado)
        except Exception as rep_err:
            logger.error(f"❌ Falló reparación del JSON: {rep_err}")
            raise je


# --- EXPORTACIONES ESTÁNDAR PARA SKILL MANAGER ---

def get_tools_schema():
    """Retorna schemas de herramientas para Gemini Function Calling."""
    return [
        {
            "name": "buscar_jurisprudencia_especializada",
            "description": "Busca jurisprudencia y normativa oficial colombiana (cortes, sisjur, senado_leyes) usando dorks web y cache. Retorna la jerarquía legal y el peso del precedente.",
            "parameters": BuscadorInput.model_json_schema()
        },
        {
            "name": "generar_ficha_jurisprudencial",
            "description": "Analiza una sentencia y extrae su ficha técnica estructurada (Ponente, hechos, problema jurídico, ratio decidendi, resuelvo).",
            "parameters": FichaJurisprudencialInput.model_json_schema()
        },
        {
            "name": "construir_linea_jurisprudencial",
            "description": "Organiza una lista de sentencias en una línea jurisprudencial temporal identificando sentencias hito (fundadoras, modificadoras, SU).",
            "parameters": LineaJurisprudencialInput.model_json_schema()
        }
    ]


def get_tools():
    """Retorna las funciones ejecutables correspondientes."""
    return [buscar_jurisprudencia_especializada, generar_ficha_jurisprudencial, construir_linea_jurisprudencial]
