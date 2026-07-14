"""
Modelo Appointment — Registro de citas agendadas por el secretario IA.
Vinculado con Lead para trazabilidad completa del embudo de ventas.
"""
from typing import Optional
from datetime import datetime, date, time
import enum
import secrets

from sqlmodel import SQLModel, Field


class AppointmentStatus(str, enum.Enum):
    """Estados del ciclo de vida de una cita."""
    PENDING = "pending"             # Creada por la IA, pendiente de confirmación humana
    CONFIRMED = "confirmed"         # Confirmada por el asesor
    RESCHEDULED = "rescheduled"     # Reprogramada
    COMPLETED = "completed"         # La reunión ocurrió
    CANCELLED = "cancelled"         # Cancelada
    NO_SHOW = "no_show"             # El cliente no asistió


class AppointmentType(str, enum.Enum):
    """Modalidad de la reunión."""
    VIDEO_CALL = "video_call"       # Zoom / Meet
    PHONE_CALL = "phone_call"       # Llamada telefónica
    IN_PERSON = "in_person"         # Presencial en oficina
    WHATSAPP = "whatsapp"           # Chat de WhatsApp


class Appointment(SQLModel, table=True):
    """
    Modelo de Cita (agendada por el secretario IA o manualmente por el admin).
    Cada cita está vinculada opcionalmente a un Lead para trazabilidad.
    """
    __tablename__ = "appointments"

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- Relación con Lead ---
    lead_id: Optional[int] = Field(default=None, foreign_key="leads.id", index=True)
    lead_email: str = Field(max_length=255, index=True)
    lead_name: Optional[str] = Field(default=None, max_length=150)

    # --- Fecha y hora ---
    appointment_date: date
    appointment_time: time
    duration_minutes: int = Field(default=30)
    timezone: str = Field(default="America/Bogota", max_length=50)

    # --- Tipo y motivo ---
    appointment_type: str = Field(
        default=AppointmentType.VIDEO_CALL.value, max_length=50
    )
    reason: str = Field(max_length=500)
    # Descripción del motivo — generada por la IA desde la conversación

    internal_notes: Optional[str] = Field(default=None, max_length=2000)
    # Resumen de la conversación del chat para contexto del asesor

    # --- Estado ---
    status: str = Field(default=AppointmentStatus.PENDING.value, max_length=50)

    # --- Links y confirmación ---
    meeting_link: Optional[str] = Field(default=None, max_length=500)
    confirmation_token: Optional[str] = Field(
        default=None, max_length=100, unique=True, index=True
    )
    # Token para que el cliente confirme/cancele sin login

    # --- Control de emails ---
    confirmation_email_sent: bool = Field(default=False)
    reminder_email_sent: bool = Field(default=False)
    # Para no enviar correos duplicados

    # --- Metadatos ---
    created_by: str = Field(default="ai_agent", max_length=100)
    # "ai_agent" o "admin_manual"

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    cancelled_at: Optional[datetime] = Field(default=None)
    cancellation_reason: Optional[str] = Field(default=None, max_length=300)

    # --- Jitsi e Integración Legal ---
    jitsi_room_name: Optional[str] = Field(default=None, max_length=150)
    jitsi_recording_cid: Optional[str] = Field(default=None, max_length=150)
    jitsi_transcription_cid: Optional[str] = Field(default=None, max_length=150)
    declaration_text: Optional[str] = Field(default=None, max_length=1000)

    def generate_token(self) -> str:
        """Genera un token único para confirmación/cancelación por email."""
        self.confirmation_token = secrets.token_urlsafe(32)
        return self.confirmation_token
