from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

# --- SCHEMAS DE ENTRADA PARA GEMINI FUNCTION CALLING ---

class JurisprudenciaInput(BaseModel):
    derecho_fundamental: str = Field(..., description="El derecho fundamental vulnerado (ej: 'salud', 'peticion', 'debido proceso', 'estabilidad laboral')")
    tipo_caso: str = Field(..., description="Breve descripción del caso para afinar los precedentes (ej: 'negacion de medicamento', 'despido sin autorizacion de inspector de trabajo')")

class ProcedibilidadInput(BaseModel):
    legitimacion_activa: str = Field(..., description="Descripción de quién presenta la tutela y su relación con el afectado (ej: 'afectado directo', 'padre en representacion de hijo menor')")
    legitimacion_pasiva: str = Field(..., description="Nombre y tipo de la entidad contra quien se dirige (ej: 'EPS Sanitas (particular que presta servicio publico)', 'Alcaldia de Bogota (autoridad publica)')")
    inmediatez_hechos: str = Field(..., description="Fecha de ocurrencia de los hechos o de la última actuación vulneradora (ej: 'hace 15 dias', 'hace 8 meses')")
    subsidiariedad_recursos: str = Field(..., description="Recursos o reclamaciones previas intentadas (ej: 'se presento derecho de peticion sin respuesta', 'ningun recurso ordinario disponible')")

class EstructurarCasoInput(BaseModel):
    relato_usuario: str = Field(..., description="El relato informal o desordenado de hechos y peticiones que proporciona el cliente")
    tipo_tramite: str = Field(..., description="Tipo de trámite ('creacion_tutela', 'creacion_peticion', 'contestacion_tutela')")


# --- IMPLEMENTACIÓN DE LAS FUNCIONES DE LAS HERRAMIENTAS ---

def obtener_jurisprudencia_y_fundamentos(derecho_fundamental: str, tipo_caso: str) -> dict:
    """
    Provee precedentes jurisprudenciales reales (Sentencias T, C y SU de la Corte Constitucional colombiana)
    y fundamentación constitucional/legal según el derecho fundamental invocado.
    """
    df_clean = derecho_fundamental.lower().strip()
    
    # Base de conocimiento jurídica integrada de precedentes hito
    db_jurisprudencia = {
        "salud": {
            "sentencias": [
                "Sentencia T-760 de 2008 (Corte Constitucional): Sentencia hito que unificó las reglas del derecho a la salud como derecho fundamental autónomo. Establece que el servicio de salud debe ser continuo, oportuno, de calidad e integral.",
                "Sentencia SU-273 de 2019 (Corte Constitucional): Precisa las reglas para el suministro de pañales, transporte y servicios no incluidos en el Plan de Beneficios en Salud (PBS) para personas en situación de discapacidad o vulnerabilidad económica.",
                "Sentencia T-027 de 2021 (Corte Constitucional): Doctrina de la continuidad en los tratamientos de salud iniciados, prohibiendo la suspensión abrupta por razones administrativas o contractuales."
            ],
            "normas": [
                "Artículo 49 de la Constitución Política de Colombia (Garantía de la salud y el saneamiento ambiental).",
                "Ley Estatutaria de Salud (Ley 1751 de 2015): Consagra la salud como derecho fundamental e irrenunciable."
            ],
            "argumento_sugerido": "La salud es un derecho de carácter fundamental y autónomo. La entidad accionada no puede invocar trámites administrativos ni falta de recursos contractuales para negar la atención integral o el suministro de tecnologías médicas ordenadas por el médico tratante."
        },
        "peticion": {
            "sentencias": [
                "Sentencia T-230 de 2020 (Corte Constitucional): Reitera los elementos del núcleo esencial del derecho de petición: la pronta resolución, la respuesta de fondo (clara, precisa y congruente) y la notificación de la decisión.",
                "Sentencia SU-213 de 2021 (Corte Constitucional): Unifica las subreglas sobre la respuesta oportuna en el marco del derecho de petición y su afectación frente a otras prerrogativas."
            ],
            "normas": [
                "Artículo 23 de la Constitución Política de Colombia (Derecho a presentar peticiones respetuosas).",
                "Ley 1755 de 2015 (Regulación estatutaria del Derecho de Petición): Establece el término general de 15 días hábiles para responder peticiones de interés general o particular."
            ],
            "argumento_sugerido": "El núcleo fundamental del derecho de petición exige una respuesta oportuna y de fondo. La falta de contestación o una contestación meramente evasiva vulnera directamente la Constitución."
        },
        "debido proceso": {
            "sentencias": [
                "Sentencia T-233 de 2021 (Corte Constitucional): Señala los alcances del debido proceso en actuaciones administrativas y judiciales, recalcando el derecho de defensa, contradicción y la prohibición de dilaciones injustificadas.",
                "Sentencia SU-201 de 2021 (Corte Constitucional): Reglas sobre la configuración de vías de hecho o defectos fácticos y procedimentales en las decisiones del Estado."
            ],
            "normas": [
                "Artículo 29 de la Constitución Política de Colombia (El debido proceso se aplicará a toda clase de actuaciones judiciales y administrativas)."
            ],
            "argumento_sugerido": "Toda actuación del Estado o de particulares con poder de imperio debe ceñirse a las formas preestablecidas en la ley. No se puede sancionar ni limitar derechos sin el agotamiento pleno de la defensa y contradicción."
        },
        "estabilidad laboral": {
            "sentencias": [
                "Sentencia SU-049 de 2017 (Corte Constitucional): Unifica el alcance de la estabilidad laboral reforzada por razones de salud (fuero de salud). Señala que no se puede despedir a un trabajador en debilidad manifiesta sin previa autorización de la Oficina del Trabajo.",
                "Sentencia SU-087 de 2022 (Corte Constitucional): Reitera la protección de estabilidad laboral reforzada para mujeres en estado de embarazo o lactancia.",
                "Sentencia SL1360-2023 (Corte Suprema de Justicia): Desarrolla el fuero de prepensionados en el sector público y privado."
            ],
            "normas": [
                "Artículo 53 de la Constitución Política (Estabilidad en el empleo, principios mínimos del estatuto del trabajo).",
                "Artículo 26 de la Ley 361 de 1997 (Protección laboral para personas con limitación física, psíquica o sensorial)."
            ],
            "argumento_sugerido": "Existe estabilidad laboral reforzada cuando el trabajador padece una afectación de salud limitante. El empleador que prescinda del trabajador en estas condiciones sin autorización del Inspector de Trabajo incurre en despido ineficaz."
        },
        "minimo vital": {
            "sentencias": [
                "Sentencia SU-290 de 2022 (Corte Constitucional): Desarrolla el concepto del mínimo vital y móvil, estableciendo que la remuneración o la mesada pensional representa la garantía de subsistencia digna del ciudadano.",
                "Sentencia T-027 de 2018 (Corte Constitucional): Conexidad del mínimo vital con la vida digna en adultos mayores a quienes se les retiene el pago de acreencias pensionales."
            ],
            "normas": [
                "Artículos 1, 11 y 53 de la Constitución Política colombiana (Garantía de vida digna, trabajo, y mínimos constitucionales)."
            ],
            "argumento_sugerido": "La afectación del mínimo vital no requiere prueba de indigencia, basta con demostrar la ausencia de ingresos regulares necesarios para suplir las necesidades básicas de alimentación, vivienda, vestuario y educación."
        }
    }
    
    # Búsqueda aproximada en el mapa
    fundamento = None
    for key in db_jurisprudencia:
        if key in df_clean:
            fundamento = db_jurisprudencia[key]
            break
            
    if not fundamento:
        # Fallback genérico en caso de que sea un derecho no parametrizado directamente
        fundamento = {
            "sentencias": [
                "Sentencia T-002 de 2021 (Corte Constitucional): Reitera los principios de supremacía constitucional y la protección reforzada de los derechos fundamentales mediante la acción de tutela en el ordenamiento colombiano."
            ],
            "normas": [
                "Artículo 86 de la Constitución Política de Colombia (Acción de tutela para la protección inmediata de los derechos fundamentales).",
                "Decreto 2591 de 1991 (Reglamento de la Acción de Tutela)."
            ],
            "argumento_sugerido": f"La tutela es el mecanismo preferente y sumario instituido para el amparo inmediato del derecho fundamental alegado, el cual goza de protección constitucional reforzada."
        }
        
    return {
        "derecho_consultado": derecho_fundamental,
        "tipo_caso": tipo_caso,
        "sentencias_precedentes": fundamento["sentencias"],
        "normas_sustento": fundamento["normas"],
        "argumentacion_propuesta": fundamento["argumento_sugerido"],
        "sugerencia_redaccion": f"Citar de forma textual las sentencias constitucionales hito aportadas. Puedes contrastar estas referencias de la Corte Constitucional usando la herramienta 'web_search' para verificar sentencias complementarias de los años 2025 o 2026 en caso de cambios normativos."
    }


def analizar_requisitos_procedibilidad_colombia(
    legitimacion_activa: str, 
    legitimacion_pasiva: str, 
    inmediatez_hechos: str, 
    subsidiariedad_recursos: str
) -> dict:
    """
    Evalúa la procedibilidad de la tutela conforme al Decreto 2591 de 1991 y la jurisprudencia constitucional, 
    indicando si el caso cumple con Inmediatez, Subsidiariedad y Legitimación.
    """
    recomendaciones = []
    apto_para_tutela = True
    
    # 1. Analizar Inmediatez
    inmediatez_alert = False
    inmediatez_lower = inmediatez_hechos.lower()
    
    # Extraer de forma simple si han pasado muchos meses
    for palabra in ["meses", "años", "año", "mes"]:
        if palabra in inmediatez_lower:
            # Buscar números
            import re
            numeros = re.findall(r'\d+', inmediatez_lower)
            if numeros:
                valor = int(numeros[0])
                if (palabra in ["meses", "mes"] and valor > 6) or palabra in ["años", "año"]:
                    inmediatez_alert = True
                    break
                    
    if inmediatez_alert:
        apto_para_tutela = False
        recomendaciones.append(
            "⚠️ ALERTA DE INMEDIATEZ: Ha transcurrido más de 6 meses desde los hechos. Para evitar que el juez declare improcedente la tutela, DEBES justificar debidamente en el escrito las razones de la demora (ej: fuerza mayor, enfermedad grave que impidió actuar, persistencia de la afectación en el tiempo, o que el accionante es un sujeto de especial protección constitucional)."
        )
    else:
        recomendaciones.append("✅ INMEDIATEZ: Los hechos son recientes, lo que justifica la urgencia de la medida constitucional.")

    # 2. Analizar Subsidiariedad
    subsidiariedad_lower = subsidiariedad_recursos.lower()
    sub_cumplida = False
    
    # Si intentó recurso o no hay otra vía
    if any(pal in subsidiariedad_lower for pal in ["no hay", "ningun", "derecho de peticion", "peticion sin respuesta", "agotado", "no existe"]):
        sub_cumplida = True
        
    if not sub_cumplida:
        recomendaciones.append(
            "⚠️ ADVERTENCIA DE SUBSIDIARIEDAD: La tutela es residual. Si el usuario tiene otra vía (como demanda ordinaria laboral o civil) y no hay un perjuicio irremediable inminente, el juez podría rechazarla. DEBES enfocar la argumentación en demostrar que los medios ordinarios son ineficaces/tardíos para proteger el derecho de forma oportuna o alegar la existencia de un Perjuicio Irremediable."
        )
    else:
        recomendaciones.append("✅ SUBSIDIARIEDAD: Se evidencia el agotamiento previo del derecho de petición o la inexistencia de otros mecanismos ordinarios idóneos para proteger el derecho con la celeridad requerida.")

    # 3. Analizar Legitimaciones
    leg_activa_lower = legitimacion_activa.lower()
    leg_pasiva_lower = legitimacion_pasiva.lower()
    
    if "representacion" in leg_activa_lower or "agencia oficiosa" in leg_activa_lower or "padre" in leg_activa_lower or "madre" in leg_activa_lower:
        recomendaciones.append("ℹ️ LEGITIMACIÓN ACTIVA: Se actúa en representación o agencia oficiosa. Asegurar adjuntar los documentos de parentesco o poder especial, o justificar que el titular no puede defenderse por sí mismo.")
    else:
        recomendaciones.append("✅ LEGITIMACIÓN ACTIVA: El afectado directo presenta la tutela en nombre propio.")
        
    # Validar que el accionado sea autoridad o particular con causales especiales
    es_particular = any(p in leg_pasiva_lower for p in ["eps", "banco", "particular", "empresa", "colegio privado"])
    if es_particular:
        recomendaciones.append(
            "ℹ️ LEGITIMACIÓN PASIVA (PARTICULAR): El accionado es un particular. Recuerda justificar en el escrito que procede la tutela por encontrarse el accionante en estado de indefensión o subordinación, o porque el particular presta un servicio público esencial (ej: salud o educación)."
        )
    else:
        recomendaciones.append("✅ LEGITIMACIÓN PASIVA: Se dirige contra una autoridad pública, plenamente procedente bajo el Art. 86 C.P.")
        
    status = "APTO" if apto_para_tutela else "REQUIERE_AJUSTES"
    
    return {
        "estado_procedibilidad": status,
        "analisis_inmediatez": "Urgente" if not inmediatez_alert else "Alerta de temporalidad",
        "analisis_subsidiariedad": "Cumplido preliminarmente" if sub_cumplida else "Riesgo de improcedencia por otra via",
        "recomendaciones_legales": recomendaciones,
        "sugerencia_escrito": "Si el estado es REQUIERE_AJUSTES, la IA debe advertir explícitamente al usuario e inyectar en el borrador las cláusulas de justificación correspondientes."
    }


def estructurar_hechos_y_pretensiones(relato_usuario: str, tipo_tramite: str) -> dict:
    """
    Procesa un relato de hechos informal y desordenado y lo estructura de forma cronológica 
    y jurídica (enunciando hechos separados y pretensiones formales en lenguaje legal colombiano).
    """
    # 1. Separar oraciones o párrafos
    parrafos = [p.strip() for p in relato_usuario.replace("\r", "").split("\n") if len(p.strip()) > 10]
    
    # Si no hay párrafos claros, separar por puntos
    if len(parrafos) <= 1:
        parrafos = [s.strip() for s in relato_usuario.split(".") if len(s.strip()) > 10]
        
    hechos_estructurados = []
    for idx, p in enumerate(parrafos):
        # Limpiar palabras informales al inicio
        p_clean = p
        for prefix in ["bueno ", "pues ", "entonces ", "y ", "que "]:
            if p_clean.lower().startswith(prefix):
                p_clean = p_clean[len(prefix):].capitalize()
                
        # Asegurar que empiece con mayúscula y termine con punto
        if not p_clean.endswith("."):
            p_clean += "."
        p_clean = p_clean[0].upper() + p_clean[1:]
        
        hechos_estructurados.append(f"{idx+1}. {p_clean}")
        
    # En caso de que no haya hechos
    if not hechos_estructurados:
        hechos_estructurados = ["1. [Describir cronológicamente el hecho vulnerador inicial aquí]."]

    # 2. Generar pretensiones sugeridas según el tipo de trámite
    pretensiones_sugeridas = []
    if tipo_tramite == "creacion_tutela":
        pretensiones_sugeridas = [
            "1. Solicito tutelar y proteger de manera inmediata el derecho fundamental invocado.",
            "2. En consecuencia, ordenar a la entidad accionada que, en el término perentorio de cuarenta y ocho (48) horas, proceda a dar respuesta definitiva, entregar el medicamento, o cesar el acto vulnerador de manera definitiva.",
            "3. (Opcional) Solicitar medida provisional para suspender los efectos perjudiciales del acto acusado durante el trámite de la presente acción."
        ]
    elif tipo_tramite == "creacion_peticion":
        pretensiones_sugeridas = [
            "1. Solicito formalmente a su despacho dar respuesta de fondo, de manera clara, oportuna y congruente con el objeto de la presente petición.",
            "2. Requiero se me expida y compulse copia física o digital de las actuaciones administrativas objeto de la presente solicitud."
        ]
    else:
        pretensiones_sugeridas = [
            "1. Solicito respetuosamente al señor Juez declarar la improcedencia o negar el amparo constitucional en razón a la inexistencia de vulneración de derechos o configuración de hecho superado."
        ]

    return {
        "tipo_tramite": tipo_tramite,
        "cantidad_hechos_detectados": len(hechos_estructurados),
        "hechos_formateados": hechos_estructurados,
        "pretensiones_formales_sugeridas": pretensiones_sugeridas,
        "consejo_redaccion": "La IA debe incorporar estos hechos y pretensiones formateados directamente en las variables de la plantilla correspondiente al generar el documento."
    }


# --- EXPORTACIONES ESTÁNDAR PARA EL SKILL MANAGER ---

def get_tools_schema():
    """Retorna los schemas de herramientas disponibles para Gemini Function Calling."""
    return [
        {
            "name": "obtener_jurisprudencia_y_fundamentos",
            "description": "Provee precedentes jurisprudenciales de la Corte Constitucional colombiana (Sentencias T y SU) y sustento normativo según el derecho fundamental vulnerado (salud, peticion, debido proceso, estabilidad laboral, minimo vital).",
            "parameters": JurisprudenciaInput.model_json_schema()
        },
        {
            "name": "analizar_requisitos_procedibilidad_colombia",
            "description": "Evalúa si una tutela cumple con los requisitos de procedibilidad en Colombia (inmediatez, subsidiariedad y legitimaciones por activa y pasiva), entregando alertas y sugerencias jurídicas claras.",
            "parameters": ProcedibilidadInput.model_json_schema()
        },
        {
            "name": "estructurar_hechos_y_pretensiones",
            "description": "Toma un relato de hechos informal y desordenado proporcionado por el usuario o cliente y lo estructura formalmente en una serie ordenada de hechos cronológicos y pretensiones con jerarquía legal.",
            "parameters": EstructurarCasoInput.model_json_schema()
        }
    ]

def get_tools():
    """Retorna las funciones ejecutables correspondientes a los schemas."""
    return [
        obtener_jurisprudencia_y_fundamentos,
        analizar_requisitos_procedibilidad_colombia,
        estructurar_hechos_y_pretensiones
    ]
