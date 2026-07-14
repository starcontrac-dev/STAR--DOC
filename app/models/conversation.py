"""
Modelo ConversationLog — Memoria persistente del agente secretario.
Guarda el historial completo de cada sesión de chat para análisis,
continuidad de conversaciones y contexto para el asesor humano.
"""
from typing import Optional
from datetime import datetime

from sqlmodel import SQLModel, Field


class ConversationLog(SQLModel, table=True):
    """
    Registro de cada turno de conversación del widget de chat.
    Permite al agente retomar conversaciones y al admin
    revisar el contexto completo antes de una cita.
    """
    __tablename__ = "conversation_logs"

    id: Optional[int] = Field(default=None, primary_key=True)

    # --- Identificación de sesión ---
    session_id: str = Field(index=True, max_length=100)
    lead_id: Optional[int] = Field(default=None, foreign_key="leads.id", index=True)

    # --- Contenido del turno ---
    role: str = Field(max_length=20)  # "user" | "assistant" | "tool"
    content: str = Field(max_length=10000)

    # --- Datos de herramientas (si aplica) ---
    tool_name: Optional[str] = Field(default=None, max_length=100)
    tool_result: Optional[str] = Field(default=None, max_length=5000)

    # --- Timestamps ---
    created_at: datetime = Field(default_factory=datetime.utcnow)
