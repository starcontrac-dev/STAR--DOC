"""
Modelo de base de datos para auditoría de llamadas a herramientas (tools) de Skills.

Permite almacenar registros de auditoría y compliance legal de todas las acciones
realizadas por el Agente de IA al invocar herramientas especializadas.
"""

from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional

class ToolAuditLog(SQLModel, table=True):
    """Registro de auditoría e integridad de llamadas a herramientas de Skills."""
    __tablename__ = "tool_audit_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
    skill_id: str = Field(index=True, max_length=64)
    tool_name: str = Field(index=True, max_length=100)
    parameters: str = Field(description="Parámetros recibidos en formato JSON")
    result: Optional[str] = Field(default=None, description="Resultado devuelto en formato JSON o texto")
    duration_ms: float = Field(description="Duración en milisegundos de la ejecución")
    success: bool = Field(index=True, description="Indica si la herramienta se ejecutó con éxito")
    error_message: Optional[str] = Field(default=None, description="Mensaje de error en caso de fallo")
