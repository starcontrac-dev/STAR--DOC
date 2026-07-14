from datetime import date
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from decimal import Decimal, ROUND_HALF_UP

class LiquidacionInput(BaseModel):
    # --- Campos originales (Compatibilidad garantizada) ---
    salario_mensual: float = Field(..., gt=0, description="Salario base mensual")
    fecha_ingreso: date = Field(..., description="Fecha de inicio del contrato")
    fecha_retiro: date = Field(..., description="Fecha de terminación del contrato")
    auxilio_transporte: float = Field(249095.0, ge=0, description="Valor del auxilio de transporte mensual si aplica (Valor 2026: 249095)")
    incluye_auxilio_en_base: bool = Field(True, description="Si el salario <= 2 SMMLV, el auxilio cuenta para prestaciones")
    tipo_contrato: str = Field("indefinido", description="Tipo de contrato: indefinido, termino_fijo, obra_labor")
    causa_retiro: str = Field("renuncia", description="Motivo: renuncia, despido_justo, despido_injusto")
    
    # --- Nuevos campos para precisión legal 2026 ---
    es_salario_integral: bool = Field(False, description="Si el contrato pactó salario integral (mínimo 13 SMMLV en total)")
    es_salario_variable: bool = Field(False, description="Si el salario presenta comisiones, recargos o variabilidad regular")
    salario_promedio_prestaciones: Optional[float] = Field(None, description="Promedio mensual para cesantías y prima (si es salario variable)")
    salario_promedio_vacaciones: Optional[float] = Field(None, description="Promedio mensual para vacaciones (si es salario variable)")
    
    # --- Cortes de causación (para no calcular desde el ingreso linealmente si ya hubo pagos previos) ---
    cesantias_pendientes_desde: Optional[date] = Field(None, description="Fecha desde la cual se adeudan cesantías e intereses")
    prima_pendiente_desde: Optional[date] = Field(None, description="Fecha desde la cual se adeuda la prima de servicios")
    dias_vacaciones_pendientes: Optional[float] = Field(None, description="Días específicos de vacaciones acumuladas pendientes de pago")
    vacaciones_disfrutadas: float = Field(0.0, ge=0, description="Días de vacaciones ya tomados por el trabajador (si no se especifica saldo pendiente)")
    
    # --- Parámetros de indemnización y sanciones ---
    fecha_fin_contrato: Optional[date] = Field(None, description="Fecha pactada de fin (Requerido para indemnización a término fijo)")
    fecha_estimada_fin_obra: Optional[date] = Field(None, description="Fecha estimada de fin de la obra (Requerido para indemnización obra/labor)")
    fecha_calculo_sancion_mora: Optional[date] = Field(None, description="Fecha para simular la sanción del Art. 65 CST si no se ha pagado")
    smmlv_vigente: float = Field(1750905.0, description="Valor del SMMLV del año de liquidación para calcular topes (2026: 1750905)")
    uvt_vigente: float = Field(50971.0, description="Valor de la UVT vigente (2026: 50971)")

def dias_laborales_comerciales(fecha_inicio: date, fecha_fin: date) -> int:
    """
    Calcula los días trabajados usando el calendario comercial colombiano (CST).
    Todos los meses se asumen de 30 días, y el año de 360 días.
    """
    if fecha_fin < fecha_inicio:
        return 0
        
    dia_inicio = min(fecha_inicio.day, 30)
    dia_fin = min(fecha_fin.day, 30)
    
    # Ajuste para febreros (estándar comercial y de nómina)
    if fecha_inicio.month == 2 and fecha_inicio.day in (28, 29):
        dia_inicio = 30
    if fecha_fin.month == 2 and fecha_fin.day in (28, 29):
        dia_fin = 30

    anos = fecha_fin.year - fecha_inicio.year
    meses = fecha_fin.month - fecha_inicio.month
    dias = dia_fin - dia_inicio

    return (anos * 360) + (meses * 30) + dias + 1

def salid_a_float(valor: Decimal) -> float:
    """Helper global para redondear y convertir Decimal a float para salida JSON."""
    return float(valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def calcular_liquidacion(input_data: LiquidacionInput) -> dict:
    """
    Calcula la liquidación laboral según la ley colombiana vigente para 2026.
    Utiliza matemática de precisión (Decimal) y el calendario comercial de 360 días.
    """
    if input_data.fecha_retiro < input_data.fecha_ingreso:
        raise ValueError("La fecha de retiro no puede ser anterior a la fecha de ingreso")

    # 1. Parámetros Generales
    smmlv = Decimal(str(input_data.smmlv_vigente))
    aux_transporte = Decimal(str(input_data.auxilio_transporte))
    uvt = Decimal(str(input_data.uvt_vigente))
    salario_mensual_dec = Decimal(str(input_data.salario_mensual))
    
    # Días totales trabajados
    dias_totales = dias_laborales_comerciales(input_data.fecha_ingreso, input_data.fecha_retiro)
    dias_totales_dec = Decimal(str(dias_totales))

    # 2. Configuración de Salario Integral
    # Mínimo 13 SMMLV (10 salario + 3 prestacional)
    es_integral = input_data.es_salario_integral
    if es_integral and salario_mensual_dec < (smmlv * Decimal('13')):
        # Si se marca integral pero no llega al tope, se procesa igual según el flag del usuario.
        pass

    # 3. Bases Salariales para Liquidar
    # Si es salario variable, usamos los promedios suministrados.
    salario_base_prestaciones = salario_mensual_dec
    salario_ordinario = salario_mensual_dec # Base vacaciones (nunca incluye auxilio de transporte)

    if input_data.es_salario_variable:
        if input_data.salario_promedio_prestaciones is not None:
            salario_base_prestaciones = Decimal(str(input_data.salario_promedio_prestaciones))
        if input_data.salario_promedio_vacaciones is not None:
            salario_ordinario = Decimal(str(input_data.salario_promedio_vacaciones))

    # A la base prestacional se le suma auxilio de transporte si aplica (salario <= 2 SMMLV y no es integral)
    auxilio_aplica = False
    if not es_integral:
        if input_data.incluye_auxilio_en_base and salario_base_prestaciones <= (smmlv * Decimal('2')):
            salario_base_prestaciones += aux_transporte
            auxilio_aplica = True

    # 4. Días a liquidar por concepto (Cortes de causación)
    # Cesantías e Intereses
    fecha_base_cesantias = input_data.cesantias_pendientes_desde or date(input_data.fecha_retiro.year, 1, 1)
    if fecha_base_cesantias < input_data.fecha_ingreso:
        fecha_base_cesantias = input_data.fecha_ingreso
    dias_cesantias = dias_laborales_comerciales(fecha_base_cesantias, input_data.fecha_retiro)
    dias_cesantias_dec = Decimal(str(dias_cesantias))

    # Prima de Servicios
    # La prima se causa semestralmente (se paga a más tardar el 30 de junio y 20 de diciembre)
    semestre_inicio = date(input_data.fecha_retiro.year, 1, 1) if input_data.fecha_retiro.month <= 6 else date(input_data.fecha_retiro.year, 7, 1)
    fecha_base_prima = input_data.prima_pendiente_desde or semestre_inicio
    if fecha_base_prima < input_data.fecha_ingreso:
        fecha_base_prima = input_data.fecha_ingreso
    dias_prima = dias_laborales_comerciales(fecha_base_prima, input_data.fecha_retiro)
    dias_prima_dec = Decimal(str(dias_prima))

    # Vacaciones
    # Se liquidan sobre los días proporcionales de todo el contrato menos lo disfrutado, o sobre saldo directo
    if input_data.dias_vacaciones_pendientes is not None:
        vacaciones_compensar_dias = Decimal(str(input_data.dias_vacaciones_pendientes))
    else:
        # 15 días de vacaciones por cada 360 días laborados
        dias_vacaciones_totales = (dias_totales_dec * Decimal('15')) / Decimal('360')
        vacaciones_compensar_dias = dias_vacaciones_totales - Decimal(str(input_data.vacaciones_disfrutadas))
        if vacaciones_compensar_dias < Decimal('0'):
            vacaciones_compensar_dias = Decimal('0')

    # 5. Cálculos de Prestaciones
    if es_integral:
        # Salario integral no causa prima, cesantías ni intereses
        cesantias = Decimal('0')
        intereses_cesantias = Decimal('0')
        prima = Decimal('0')
        # Vacaciones se liquidan sobre el 70% del salario integral
        base_vacaciones_integral = salario_ordinario * Decimal('0.70')
        vacaciones = (base_vacaciones_integral * vacaciones_compensar_dias) / Decimal('30')
    else:
        cesantias = (salario_base_prestaciones * dias_cesantias_dec) / Decimal('360')
        intereses_cesantias = (cesantias * dias_cesantias_dec * Decimal('0.12')) / Decimal('360')
        prima = (salario_base_prestaciones * dias_prima_dec) / Decimal('360')
        vacaciones = (salario_ordinario * vacaciones_compensar_dias) / Decimal('30')

    # 6. Cálculo de Indemnización (Art. 64 CST)
    indemnizacion = Decimal('0')
    base_indemnizacion = salario_ordinario * Decimal('0.70') if es_integral else salario_ordinario
    salario_diario_indemnizacion = base_indemnizacion / Decimal('30')

    if input_data.causa_retiro == "despido_injusto":
        if input_data.tipo_contrato == "indefinido":
            # Para contratos indefinidos, la indemnización depende de si se devengan menos o más de 10 SMMLV
            tope_10_smmlv = smmlv * Decimal('10')
            
            if base_indemnizacion < tope_10_smmlv:
                # Menos de 10 SMMLV: 30 días por el primer año o fracción, y 20 por los siguientes.
                if dias_totales_dec <= Decimal('360'):
                    # Si tiene menos de 1 año, por jurisprudencia se pagan los 30 días completos.
                    indemnizacion = Decimal('30') * salario_diario_indemnizacion
                else:
                    dias_adicionales = dias_totales_dec - Decimal('360')
                    fraccion_proporcional = dias_adicionales / Decimal('360')
                    indemnizacion = (Decimal('30') * salario_diario_indemnizacion) + (Decimal('20') * salario_diario_indemnizacion * fraccion_proporcional)
            else:
                # 10 SMMLV o más: 20 días por el primer año o fracción, y 15 por los siguientes.
                if dias_totales_dec <= Decimal('360'):
                    indemnizacion = Decimal('20') * salario_diario_indemnizacion
                else:
                    dias_adicionales = dias_totales_dec - Decimal('360')
                    fraccion_proporcional = dias_adicionales / Decimal('360')
                    indemnizacion = (Decimal('20') * salario_diario_indemnizacion) + (Decimal('15') * salario_diario_indemnizacion * fraccion_proporcional)

        elif input_data.tipo_contrato == "termino_fijo":
            # Salarios correspondientes al tiempo que falte para cumplir el plazo pactado
            if input_data.fecha_fin_contrato and input_data.fecha_fin_contrato > input_data.fecha_retiro:
                dias_faltantes = dias_laborales_comerciales(input_data.fecha_retiro, input_data.fecha_fin_contrato) - 1
                indemnizacion = salario_diario_indemnizacion * Decimal(str(dias_faltantes))

        elif input_data.tipo_contrato == "obra_labor":
            # Salarios correspondientes al tiempo que falte para terminar la obra. Mínimo legal de 15 días.
            if input_data.fecha_estimada_fin_obra and input_data.fecha_estimada_fin_obra > input_data.fecha_retiro:
                dias_faltantes = dias_laborales_comerciales(input_data.fecha_retiro, input_data.fecha_estimada_fin_obra) - 1
                indemnizacion = salario_diario_indemnizacion * Decimal(str(dias_faltantes))
                if indemnizacion < Decimal('15') * salario_diario_indemnizacion:
                    indemnizacion = Decimal('15') * salario_diario_indemnizacion
            else:
                # Si no se tiene fecha estimada, se aplica el piso legal de 15 días.
                indemnizacion = Decimal('15') * salario_diario_indemnizacion

    # 7. Estimación de Sanción Moratoria (Art. 65 CST)
    sancion_moratoria = Decimal('0')
    mora_intereses = Decimal('0')
    dias_mora = 0
    
    fecha_calculo_mora = input_data.fecha_calculo_sancion_mora or date.today()
    if fecha_calculo_mora > input_data.fecha_retiro:
        dias_mora = (fecha_calculo_mora - input_data.fecha_retiro).days
        
        # Sanción: 1 día de salario por cada día de mora hasta por 24 meses (720 días).
        # A partir del día 721:
        # - Si salario <= 10 SMMLV: Continúa sumando 1 día de salario por día de mora.
        # - Si salario > 10 SMMLV: Se detiene la sanción y corren intereses moratorios sobre el saldo de prestaciones.
        salario_diario = salario_mensual_dec / Decimal('30')
        total_deuda_prestaciones = cesantias + intereses_cesantias + prima + vacaciones
        
        if dias_mora <= 720:
            sancion_moratoria = Decimal(str(dias_mora)) * salario_diario
        else:
            if salario_mensual_dec <= (smmlv * Decimal('10')):
                sancion_moratoria = Decimal(str(dias_mora)) * salario_diario
            else:
                sancion_moratoria = Decimal('720') * salario_diario
                # Interés moratorio anual promedio estimado de la Superfinanciera (28% E.A.)
                tasa_diaria = Decimal('0.28') / Decimal('360')
                dias_excedentes = Decimal(str(dias_mora - 720))
                mora_intereses = total_deuda_prestaciones * tasa_diaria * dias_excedentes

    # 8. Retención en la fuente sobre indemnizaciones (Art. 401-3 E.T.)
    retencion_fuente = Decimal('0')
    if indemnizacion > 0:
        limite_exento_uvt = Decimal('204')
        monto_exento = limite_exento_uvt * uvt
        
        # En Colombia, los trabajadores que devengan menos de 10 SMMLV usualmente no están sujetos a la
        # retención del 20% sobre la indemnización laboral. Si es >= 10 SMMLV se aplica sobre el exceso.
        if base_indemnizacion >= (smmlv * Decimal('10')):
            if indemnizacion > monto_exento:
                exceso = indemnizacion - monto_exento
                retencion_fuente = exceso * Decimal('0.20')

    # 9. Seguridad Social Informativa del Último Periodo (1 mes laboral base)
    # Se calcula sobre el salario ordinario básico (sin auxilio de transporte)
    ibc = salario_ordinario
    
    # Aportes Trabajador: Salud 4%, Pensión 4%
    salud_trabajador = ibc * Decimal('0.04')
    pension_trabajador = ibc * Decimal('0.04')
    
    # Aportes Empleador: Salud 8.5% (exento si salario < 10 SMMLV y es persona jurídica), Pensión 12%, ARL Clase I 0.522%
    # Parafiscales: Caja de Compensación 4%, SENA 2% (exento), ICBF 3% (exento)
    exento_parafiscales_ss = ibc < (smmlv * Decimal('10'))
    
    salud_empleador = Decimal('0') if exento_parafiscales_ss else (ibc * Decimal('0.085'))
    pension_empleador = ibc * Decimal('0.12')
    arl_empleador = ibc * Decimal('0.00522') # Nivel de riesgo I standard
    
    caja_compensacion = ibc * Decimal('0.04')
    sena_empleador = Decimal('0') if exento_parafiscales_ss else (ibc * Decimal('0.02'))
    icbf_empleador = Decimal('0') if exento_parafiscales_ss else (ibc * Decimal('0.03'))
    
    seguridad_social_info = {
        "salud_trabajador": float(salid_a_float(salud_trabajador)),
        "pension_trabajador": float(salid_a_float(pension_trabajador)),
        "salud_empleador": float(salid_a_float(salud_empleador)),
        "pension_empleador": float(salid_a_float(pension_empleador)),
        "arl_empleador": float(salid_a_float(arl_empleador)),
        "caja_compensacion": float(salid_a_float(caja_compensacion)),
        "sena": float(salid_a_float(sena_empleador)),
        "icbf": float(salid_a_float(icbf_empleador)),
        "exento_impuestos_nomina": exento_parafiscales_ss
    }

    # 10. Totales
    total_prestaciones = cesantias + intereses_cesantias + prima + vacaciones
    neto_recibir = total_prestaciones
    if input_data.causa_retiro == "despido_injusto":
        neto_recibir += (indemnizacion - retencion_fuente)

    # Estructurar la salida para la API
    return {
        "dias_trabajados_totales": dias_totales,
        "dias_cesantias_liquidadas": dias_cesantias,
        "dias_prima_liquidadas": dias_prima,
        "dias_vacaciones_compensadas": float(vacaciones_compensar_dias.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
        "cesantias": salid_a_float(cesantias),
        "intereses_cesantias": salid_a_float(intereses_cesantias),
        "prima": salid_a_float(prima),
        "vacaciones": salid_a_float(vacaciones),
        "total_prestaciones": salid_a_float(total_prestaciones),
        "indemnizacion": salid_a_float(indemnizacion) if indemnizacion > 0 else None,
        "retencion_fuente_indemnizacion": salid_a_float(retencion_fuente) if retencion_fuente > 0 else None,
        "neto_a_recibir": salid_a_float(neto_recibir),
        "sancion_moratoria_estimada": salid_a_float(sancion_moratoria) if sancion_moratoria > 0 else None,
        "sancion_mora_intereses": salid_a_float(mora_intereses) if mora_intereses > 0 else None,
        "dias_mora": dias_mora,
        "seguridad_social_informativa": seguridad_social_info,
        "es_salario_integral": es_integral,
        "auxilio_transporte_aplicado": auxilio_aplica
    }