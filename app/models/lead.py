"""
Modelo Lead — Captura de prospectos desde el widget de chat IA.
Almacena información de contacto de visitantes interesados
recolectada de forma natural por el agente secretario.
"""
from typing import Optional
from datetime import datetime
import enum

from sqlmodel import SQLModel, Field


class LeadStatus(str, enum.Enum):
    """Estados del ciclo de vida de un lead."""
    NEW = "new"                     # Recién capturado por la IA
    CONTACTED = "contacted"         # Se le envió un correo o se contactó
    QUALIFIED = "qualified"         # Confirmó interés real
    APPOINTED = "appointed"         # Tiene cita agendada
    CONVERTED = "converted"         # Se convirtió en cliente
    DISCARDED = "discarded"         # No calificó o no respondió


class LeadSource(str, enum.Enum):
    """Fuente de donde proviene el lead."""
    CHAT_WIDGET = "chat_widget"
    WHATSAPP = "whatsapp"
    FORM = "form"
    REFERRAL = "referral"
    ORGANIC = "organic"


class Lead(SQLModel, table=True):
    """
    Modelo de Lead (prospecto de ventas).
    Capturado automáticamente por el agente secretario IA
    a través del widget de chat en la landing page.
    """
    __tablename__ = "leads"

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- Datos de contacto ---
    email: str = Field(index=True, unique=True, max_length=255)
    name: Optional[str] = Field(default=None, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=30)
    company: Optional[str] = Field(default=None, max_length=200)

    # --- Intención y contexto ---
    service_interest: Optional[str] = Field(default=None, max_length=300)
    # Ej: "Consulta divorcio", "Contrato comercial", "Defensa penal"

    initial_message: Optional[str] = Field(default=None, max_length=2000)
    # El primer mensaje que escribió el usuario — muy valioso para el asesor humano

    # --- Clasificación ---
    status: str = Field(default=LeadStatus.NEW.value, max_length=20)
    source: str = Field(default=LeadSource.CHAT_WIDGET.value, max_length=20)
    priority: int = Field(default=3)  # 1=alta, 2=media, 3=normal

    # --- Metadatos de sesión ---
    session_id: Optional[str] = Field(default=None, max_length=100, index=True)
    # Para vincular con la conversación del chat

    ip_address: Optional[str] = Field(default=None, max_length=50)
    user_agent: Optional[str] = Field(default=None, max_length=500)

    # --- Control de privacidad (Habeas Data Colombia - Ley 1581/2012) ---
    gdpr_consent: bool = Field(default=False)
    gdpr_consent_at: Optional[datetime] = Field(default=None)

    # --- Notas del asesor humano ---
    notes: Optional[str] = Field(default=None, max_length=3000)

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_contact_at: Optional[datetime] = Field(default=None)
