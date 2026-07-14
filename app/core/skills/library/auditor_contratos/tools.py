from pydantic import BaseModel, Field
try:
    from app.core.tools import calculadora_terminos
except ImportError:
    calculadora_terminos = None

class AuditorTerminosInput(BaseModel):
    fecha_inicio: str = Field(..., description="Fecha inicio YYYY-MM-DD")
    dias: int = Field(..., description="Días hábiles contractuales")

async def validar_terminos_contrato(fecha_inicio: str, dias: int) -> dict:
    if not calculadora_terminos:
        return {"error": "Herramienta calculadora_terminos no disponible en el sistema."}
    try:
        import datetime
        dt = datetime.datetime.strptime(fecha_inicio, "%Y-%m-%d").date()
        fecha_fin = calculadora_terminos.calcular_dias_habiles(fecha_inicio=dt, dias=dias, jurisdiccion="colombia")
        return {"valido": True, "fecha_vencimiento_habil": str(fecha_fin)}
    except Exception as e:
        return {"valido": False, "error": str(e)}

def get_tools_schema():
    return [{
        "name": "validar_terminos_contrato",
        "description": "Calcula si un plazo en días hábiles es correcto en Colombia.",
        "parameters": AuditorTerminosInput.model_json_schema()
    }]

def get_tools(): return [validar_terminos_contrato]
