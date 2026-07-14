# -*- coding: utf-8 -*-
"""
Router de Text-to-Speech (TTS) para STAR-DOC.
Expone endpoints REST para generar audio, listar voces y obtener configuración.
"""

import logging
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.schemas.tts import TTSRequest, TTSVoice, TTSVoicesResponse, TTSSettingsResponse
from app.services.tts_service import tts_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["TTS - Text to Speech"])


@router.post("/api/tts/speak")
async def speak(request: TTSRequest):
    """
    Genera audio TTS a partir de texto.
    
    Retorna un StreamingResponse con audio MP3 usando edge-tts (primario)
    o gTTS (fallback) según disponibilidad y configuración.
    
    - **text**: Texto a convertir (1-5000 caracteres)
    - **voice**: Voz a usar (default: es-CO-SalomeNeural)
    - **rate**: Velocidad del habla (ej: '-20%', '+50%')
    - **volume**: Volumen (ej: '-30%', '+20%')
    - **pitch**: Tono (ej: '-10Hz', '+20Hz')
    - **provider**: 'auto', 'edge' o 'gtts'
    """
    logger.info(
        f"[TTS] Solicitud recibida: {len(request.text)} chars, "
        f"voz={request.voice}, provider={request.provider}"
    )

    try:
        return StreamingResponse(
            tts_service.speak(
                text=request.text,
                voice=request.voice,
                rate=request.rate,
                volume=request.volume,
                pitch=request.pitch,
                provider=request.provider
            ),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=tts_audio.mp3",
                "Cache-Control": "no-cache",
            }
        )

    except Exception as e:
        logger.error(f"[TTS] Error en speak: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generando audio TTS: {str(e)}"
        )


@router.get("/api/tts/voices", response_model=TTSVoicesResponse)
async def list_voices(locale: str = "es"):
    """
    Lista las voces TTS disponibles filtradas por idioma.
    
    - **locale**: Prefijo del idioma para filtrar (default: 'es')
    """
    try:
        voices_data = await tts_service.list_voices(locale_filter=locale)
        voices = [
            TTSVoice(
                name=v.get("name", ""),
                short_name=v.get("short_name", ""),
                gender=v.get("gender", ""),
                locale=v.get("locale", ""),
                friendly_name=v.get("friendly_name", ""),
            )
            for v in voices_data
        ]
        return TTSVoicesResponse(
            voices=voices,
            count=len(voices),
            provider="edge-tts"
        )

    except Exception as e:
        logger.error(f"[TTS] Error listando voces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo voces: {str(e)}"
        )


@router.get("/api/tts/settings", response_model=TTSSettingsResponse)
async def get_settings():
    """
    Retorna la configuración actual del servicio TTS.
    """
    return TTSSettingsResponse(
        default_voice="es-CO-SalomeNeural",
        available_providers=["edge-tts", "gtts"],
        max_text_length=5000,
        supported_locales=["es-CO", "es-MX", "es-ES", "es-AR", "en-US"]
    )


@router.get("/api/tts/metrics")
async def get_tts_metrics():
    """
    Retorna métricas de uso del servicio TTS.
    """
    return tts_service.get_metrics()
