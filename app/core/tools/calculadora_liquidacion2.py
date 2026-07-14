from datetime import date
from pydantic import BaseModel, Field
from typing import Optional

class LiquidacionInput(BaseModel):
    salario_mensual: float = Field(..., gt=0, description="Salario base mensual")
    fecha_ingreso: date = Field(..., description="Fecha de inicio del contrato")
    fecha_retiro: date = Field(..., description="Fecha de terminación del contrato")
    auxilio_transporte: float = Field(0, ge=0, description="Valor del auxilio de transporte mensual si aplica")
    incluye_auxilio_en_base: bool = Field(False, description="Si el salario es menor o igual a 2 SMMLV, el auxilio cuenta para prestaciones")
    tipo_contrato: str = Field("indefinido", description="Tipo de contrato: indefinido, termino_fijo, obra_labor")
    causa_retiro: str = Field("renuncia", description="Motivo: renuncia, despido_justo, despido_injusto")

def calcular_liquidacion(input_data: LiquidacionInput) -> dict:
    """
    Calcula la liquidación laboral según la ley colombiana.
    Nota: Las fórmulas asumen un año de 360 días para pagos comerciales y meses de 30 días.
    """
    # Validar fechas
    if input_data.fecha_retiro < input_data.fecha_ingreso:
        raise ValueError("La fecha de retiro no puede ser anterior a la fecha de ingreso")

    # Días trabajados (se suma 1 día por convención laboral en Colombia)
    dias_trabajados = (input_data.fecha_retiro - input_data.fecha_ingreso).days + 1

    # Salario base para prestaciones (Cesantías, Intereses y Prima integran auxilio)
    salario_base_prestaciones = input_data.salario_mensual
    if input_data.incluye_auxilio_en_base:
        salario_base_prestaciones += input_data.auxilio_transporte

    # Salario ordinario para Vacaciones (No incluyen auxilio de transporte jamás)
    salario_ordinario = input_data.salario_mensual

    # Cálculos
    cesantias = (salario_base_prestaciones * dias_trabajados) / 360
    intereses_cesantias = (cesantias * dias_trabajados * 0.12) / 360
    prima = (salario_base_prestaciones * dias_trabajados) / 360
    vacaciones = (salario_ordinario * dias_trabajados) / 720

    # Indemnización (Cálculo básico contrato indefinido despidiendo sin justa causa)
    indemnizacion = None
    if input_data.causa_retiro == "despido_injusto" and input_data.tipo_contrato == "indefinido":
        salario_diario = input_data.salario_mensual / 30
        anos_trabajados = dias_trabajados / 360

        # Regla: Más o menos de 10 SMMLV (Acá tomaremos 13.000.000 COP como tope aproximado para 10 SMMLV en 2024/2025)
        # O por simplicidad como regla general para salarios estándar
        if input_data.salario_mensual < 13000000:
            if anos_trabajados <= 1:
                indemnizacion = 30 * salario_diario
            else:
                indemnizacion = (30 * salario_diario) + (20 * salario_diario * (anos_trabajados - 1))
        else:
            if anos_trabajados <= 1:
                indemnizacion = 20 * salario_diario
            else:
                indemnizacion = (20 * salario_diario) + (15 * salario_diario * (anos_trabajados - 1))

    return {
        "dias_trabajados": dias_trabajados,
        "cesantias": round(cesantias, 2),
        "intereses_cesantias": round(intereses_cesantias, 2),
        "prima": round(prima, 2),
        "vacaciones": round(vacaciones, 2),
        "indemnizacion": round(indemnizacion, 2) if indemnizacion else None,
        "total_prestaciones": round(cesantias + intereses_cesantias + prima + vacaciones, 2)
    }
