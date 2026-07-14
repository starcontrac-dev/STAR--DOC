from datetime import date, datetime
import holidays
import workdays

def _parse_fecha(fecha) -> date:
    """Convierte string YYYY-MM-DD a objeto date si es necesario."""
    if isinstance(fecha, str):
        return datetime.strptime(fecha, "%Y-%m-%d").date()
    return fecha

def es_dia_habil(fecha) -> dict:
    """Verifica si una fecha es un día hábil en Colombia (L-V, no festivo)."""
    fecha = _parse_fecha(fecha)
    # Lunes=0, Domingo=6. Fines de semana son 5 y 6.
    if fecha.weekday() >= 5:
        return {"fecha": str(fecha), "es_habil": False, "motivo": "Fin de semana"}
    # Festivos Colombia
    co_holidays = holidays.Colombia(years=fecha.year)
    if fecha in co_holidays:
        return {"fecha": str(fecha), "es_habil": False, "motivo": f"Festivo: {co_holidays.get(fecha)}"}
    return {"fecha": str(fecha), "es_habil": True, "motivo": "Día hábil"}

def calcular_dias_habiles(fecha_inicio, dias: int) -> dict:
    """
    Calcula una fecha futura sumando N días hábiles, saltando Sábados, Domingos
    y Festivos en Colombia.
    """
    fecha_inicio = _parse_fecha(fecha_inicio)
    co_holidays = holidays.Colombia(years=[fecha_inicio.year, fecha_inicio.year + 1, fecha_inicio.year + 2])
    lista_festivos = list(co_holidays.keys())
    
    # La fecha calculada usando la librería workdays
    fecha_fin = workdays.workday(fecha_inicio, dias, lista_festivos)
    return {
        "fecha_inicio": str(fecha_inicio),
        "dias_habiles": dias,
        "fecha_resultado": str(fecha_fin)
    }

