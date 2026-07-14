from pydantic import BaseModel, Field
from typing import Optional
import datetime

try:
    from app.core.tools import calculadora_liquidacion
except ImportError:
    calculadora_liquidacion = None

class LiquidacionInput(BaseModel):
    salario_mensual: float = Field(..., description="Salario básico devengado mensual (en COP)")
    fecha_ingreso: str = Field(..., description="Fecha de inicio labores (formato YYYY-MM-DD)")
    fecha_retiro: str = Field(..., description="Fecha fin labores o retiro (formato YYYY-MM-DD)")
    tiene_auxilio_transporte: bool = Field(True, description="Indica si devenga auxilio de transporte (salarios <= 2 SMMLV)")
    
    # --- Parámetros Avanzados ---
    es_salario_integral: bool = Field(False, description="Determina si el trabajador pactó salario integral (mínimo 13 SMMLV)")
    es_salario_variable: bool = Field(False, description="Indica si el salario presenta comisiones o variabilidad regular")
    salario_promedio_prestaciones: Optional[float] = Field(None, description="Promedio mensual para cesantías y prima (obligatorio si es salario variable)")
    salario_promedio_vacaciones: Optional[float] = Field(None, description="Promedio mensual para vacaciones (obligatorio si es salario variable)")
    
    # --- Cortes de causación (Liquidación Realista) ---
    cesantias_pendientes_desde: Optional[str] = Field(None, description="Fecha desde la cual se adeudan cesantías (formato YYYY-MM-DD)")
    prima_pendiente_desde: Optional[str] = Field(None, description="Fecha desde la cual se adeuda la prima (formato YYYY-MM-DD)")
    dias_vacaciones_pendientes: Optional[float] = Field(None, description="Saldo específico de días de vacaciones acumuladas pendientes de pago")
    vacaciones_disfrutadas: float = Field(0.0, description="Días de vacaciones ya disfrutadas/tomadas a lo largo del contrato")
    
    # --- Parámetros de indemnización y sanción ---
    tipo_contrato: str = Field("indefinido", description="Tipo de contrato: indefinido, termino_fijo, obra_labor")
    causa_retiro: str = Field("renuncia", description="Motivo del retiro: renuncia, despido_justo, despido_injusto")
    fecha_fin_contrato: Optional[str] = Field(None, description="Fecha pactada de finalización para contratos a término fijo (formato YYYY-MM-DD)")
    fecha_estimada_fin_obra: Optional[str] = Field(None, description="Fecha estimada de finalización para contratos de obra o labor (formato YYYY-MM-DD)")
    fecha_calculo_sancion_mora: Optional[str] = Field(None, description="Fecha a la cual calcular la sanción del Art. 65 si no se ha pagado (formato YYYY-MM-DD)")

async def calcular_liquidacion_laboral(
    salario_mensual: float,
    fecha_ingreso: str,
    fecha_retiro: str,
    tiene_auxilio_transporte: bool = True,
    es_salario_integral: bool = False,
    es_salario_variable: bool = False,
    salario_promedio_prestaciones: Optional[float] = None,
    salario_promedio_vacaciones: Optional[float] = None,
    cesantias_pendientes_desde: Optional[str] = None,
    prima_pendiente_desde: Optional[str] = None,
    dias_vacaciones_pendientes: Optional[float] = None,
    vacaciones_disfrutadas: float = 0.0,
    tipo_contrato: str = "indefinido",
    causa_retiro: str = "renuncia",
    fecha_fin_contrato: Optional[str] = None,
    fecha_estimada_fin_obra: Optional[str] = None,
    fecha_calculo_sancion_mora: Optional[str] = None
) -> dict:
    """
    Calcula el neto de prestaciones laborales, vacaciones, indemnización por despido injustificado,
    sanción moratoria y aportes parafiscales en Colombia bajo la normativa del CST vigente para 2026.
    """
    if not calculadora_liquidacion:
         return {"error": "Módulo calculadora_liquidacion no encontrado."}
    try:
        # Helper para parsear fechas seguras
        def parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
            if not date_str:
                return None
            return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

        inicio = parse_date(fecha_ingreso)
        fin = parse_date(fecha_retiro)
        
        if not inicio or not fin:
            return {"error": "Las fechas de ingreso y retiro son requeridas y deben tener formato YYYY-MM-DD."}

        # Construir objeto input del motor matemático
        input_data = calculadora_liquidacion.LiquidacionInput(
            salario_mensual=salario_mensual,
            fecha_ingreso=inicio,
            fecha_retiro=fin,
            auxilio_transporte=249095.0 if tiene_auxilio_transporte else 0.0,
            incluye_auxilio_en_base=tiene_auxilio_transporte,
            es_salario_integral=es_salario_integral,
            es_salario_variable=es_salario_variable,
            salario_promedio_prestaciones=salario_promedio_prestaciones,
            salario_promedio_vacaciones=salario_promedio_vacaciones,
            cesantias_pendientes_desde=parse_date(cesantias_pendientes_desde),
            prima_pendiente_desde=parse_date(prima_pendiente_desde),
            dias_vacaciones_pendientes=dias_vacaciones_pendientes,
            vacaciones_disfrutadas=vacaciones_disfrutadas,
            tipo_contrato=tipo_contrato,
            causa_retiro=causa_retiro,
            fecha_fin_contrato=parse_date(fecha_fin_contrato),
            fecha_estimada_fin_obra=parse_date(fecha_estimada_fin_obra),
            fecha_calculo_sancion_mora=parse_date(fecha_calculo_sancion_mora)
        )
        
        # Ejecutar y retornar el resultado completo del motor
        return calculadora_liquidacion.calcular_liquidacion(input_data)
        
    except Exception as e:
        return {"error": f"Error en cálculo de liquidación: {str(e)}"}

def get_tools_schema():
    return [{
        "name": "calcular_liquidacion_laboral",
        "description": "Calcula de forma exacta las prestaciones sociales, indemnización, retención tributaria y sanción moratoria en Colombia (2026).",
        "parameters": LiquidacionInput.model_json_schema()
    }]

def get_tools(): 
    return [calcular_liquidacion_laboral]
