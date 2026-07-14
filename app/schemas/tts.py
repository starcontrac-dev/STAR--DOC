# -*- coding: utf-8 -*-
"""
Schemas Pydantic para el servicio de Text-to-Speech (TTS).
Define los modelos de validación para requests, respuestas y configuración.
"""

from pydantic import BaseModel, Field
from typing import Optional, List


class TTSRequest(BaseModel):
    """Modelo de solicitud para generar audio TTS."""
    text: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="Texto a convertir en audio. Máximo 8000 caracteres."
    )
    voice: str = Field(
        default="es-MX-JorgeNeural",
        description="Nombre de la voz a utilizar (ej: 'es-CO-SalomeNeural')."
    )
    rate: str = Field(
        default="+20%",
        description="Velocidad del habla (ej: '-20%', '+50%')."
    )
    volume: str = Field(
        default="+0%",
        description="Volumen del audio (ej: '-30%', '+20%')."
    )
    pitch: str = Field(
        default="+0Hz",
        description="Tono de la voz (ej: '-10Hz', '+20Hz')."
    )
    provider: str = Field(
        default="auto",
        description="Proveedor TTS: 'auto' (edge primero, gtts fallback), 'edge', o 'gtts'."
    )


class TTSVoice(BaseModel):
    """Modelo de una voz TTS disponible."""
    name: str = Field(..., description="Nombre técnico de la voz.")
    short_name: str = Field(..., description="Nombre corto de la voz.")
    gender: str = Field(..., description="Género: 'Male' o 'Female'.")
    locale: str = Field(..., description="Código de idioma/región (ej: 'es-CO').")
    friendly_name: str = Field(default="", description="Nombre amigable para mostrar.")


class TTSVoicesResponse(BaseModel):
    """Respuesta con la lista de voces disponibles."""
    voices: List[TTSVoice] = Field(default_factory=list)
    count: int = Field(default=0)
    provider: str = Field(default="edge-tts")


class TTSSettingsResponse(BaseModel):
    """Configuración actual del servicio TTS."""
    default_voice: str = Field(default="es-MX-JorgeNeural")
    available_providers: List[str] = Field(default_factory=lambda: ["edge-tts", "gtts"])
    max_text_length: int = Field(default=8000)
    supported_locales: List[str] = Field(
        default_factory=lambda: ["es-CO", "es-MX", "es-ES", "es-AR", "en-US"]
    )
