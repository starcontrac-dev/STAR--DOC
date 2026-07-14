"""
Modelo AvailableSlot — Disponibilidad para citas.
El administrador define desde el panel cuándo está disponible para consultas.
El secretario IA consulta estos slots antes de ofrecer horarios al visitante.
"""
from typing import Optional
from datetime import datetime, date, time

from sqlmodel import SQLModel, Field


class AvailableSlot(SQLModel, table=True):
    """
    Modelo de slot de disponibilidad.
    Cada registro representa un bloque de tiempo disponible para citas.
    La IA consulta estos slots con `check_availability` antes de proponer horarios.
    """
    __tablename__ = "available_slots"

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- Fecha y hora del slot ---
    slot_date: date = Field(index=True)
    slot_time: time
    duration_minutes: int = Field(default=30)

    # --- Estado de reserva ---
    is_booked: bool = Field(default=False)
    appointment_id: Optional[int] = Field(
        default=None, foreign_key="appointments.id"
    )

    # --- Bloqueo manual del admin ---
    is_blocked: bool = Field(default=False)
    block_reason: Optional[str] = Field(default=None, max_length=200)

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
