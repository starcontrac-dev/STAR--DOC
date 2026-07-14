# -*- coding: utf-8 -*-
"""
Servicio de Text-to-Speech (TTS) para STAR-DOC.
Implementa patrón Provider con fallback automático:
  - EdgeTTSProvider (primario): Microsoft Edge TTS, streaming, alta calidad
  - GTTSProvider (fallback): Google TTS, buffer completo
"""

import io
import logging
import time
import asyncio
import sys
from typing import AsyncGenerator, List, Dict, Any, Optional

# --- Fix for EdgeTTS on Windows/Python 3.13 ---
# Force aiohttp to use the native threaded resolver by hiding aiodns
# This avoids the 'Channel.getaddrinfo' signature mismatch error
if sys.platform == 'win32':
    sys.modules['aiodns'] = None
# ----------------------------------------------

logger = logging.getLogger(__name__)


# =============================================================================
# PROVEEDOR EDGE-TTS (PRIMARIO)
# =============================================================================

class EdgeTTSProvider:
    """
    Proveedor TTS usando Microsoft Edge.
    Genera audio MP3 en streaming sin necesidad de API key.
    """

    def __init__(self):
        self.name = "edge-tts"
        self._available = None

    def _get_unverified_connector(self):
        """Crea un conector HTTP que ignora la validación de certificados SSL para evitar errores locales de tiempo."""
        import aiohttp
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return aiohttp.TCPConnector(ssl=ssl_context)

    async def is_available(self) -> bool:
        """Verifica si edge-tts está instalado y funcional."""
        if self._available is not None:
            return self._available
        try:
            import edge_tts
            self._available = True
        except ImportError:
            logger.warning("edge-tts no está instalado. Instalar con: pip install edge-tts")
            self._available = False
        return self._available

    async def generate_stream(
        self,
        text: str,
        voice: str = "es-MX-JorgeNeural",
        rate: str = "+20%",
        volume: str = "+0%",
        pitch: str = "+0Hz"
    ) -> AsyncGenerator[bytes, None]:
        """
        Genera audio MP3 en streaming.
        
        Args:
            text: Texto a convertir en audio
            voice: Nombre de la voz (ej: 'es-CO-SalomeNeural')
            rate: Velocidad del habla (ej: '-20%', '+50%')
            volume: Volumen (ej: '-30%', '+20%')
            pitch: Tono (ej: '-10Hz', '+20Hz')
            
        Yields:
            Chunks de audio MP3 en bytes
        """
        import edge_tts

        start_time = time.time()
        total_bytes = 0

        try:
            connector = self._get_unverified_connector()
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
                connector=connector
            )

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    total_bytes += len(chunk["data"])
                    yield chunk["data"]

            elapsed = time.time() - start_time
            logger.info(
                f"[EdgeTTS] Audio generado: {total_bytes} bytes, "
                f"voz={voice}, duración={elapsed:.2f}s"
            )

        except Exception as e:
            logger.error(f"[EdgeTTS] Error generando audio: {e}")
            raise

    async def list_voices(self, locale_filter: str = "es") -> List[Dict[str, Any]]:
        """
        Lista voces disponibles filtradas por idioma.
        
        Args:
            locale_filter: Prefijo del locale para filtrar (ej: 'es', 'en')
            
        Returns:
            Lista de diccionarios con información de cada voz
        """
        import edge_tts

        try:
            connector = self._get_unverified_connector()
            voices = await edge_tts.list_voices(connector=connector)
            filtered = [
                {
                    "name": v.get("Name", ""),
                    "short_name": v.get("ShortName", ""),
                    "gender": v.get("Gender", ""),
                    "locale": v.get("Locale", ""),
                    "friendly_name": v.get("FriendlyName", ""),
                }
                for v in voices
                if v.get("Locale", "").startswith(locale_filter)
            ]
            logger.info(f"[EdgeTTS] {len(filtered)} voces encontradas para locale '{locale_filter}'")
            return filtered

        except Exception as e:
            logger.error(f"[EdgeTTS] Error listando voces: {e}")
            return []


# =============================================================================
# PROVEEDOR GTTS (FALLBACK)
# =============================================================================

class GTTSProvider:
    """
    Proveedor TTS usando Google Text-to-Speech.
    Genera audio MP3 completo en buffer (sin streaming nativo).
    """

    def __init__(self):
        self.name = "gtts"
        self._available = None

    async def is_available(self) -> bool:
        """Verifica si gTTS está instalado."""
        if self._available is not None:
            return self._available
        try:
            from gtts import gTTS
            self._available = True
        except ImportError:
            logger.warning("gTTS no está instalado. Instalar con: pip install gTTS")
            self._available = False
        return self._available

    async def generate_audio(self, text: str, lang: str = "es") -> bytes:
        """
        Genera audio MP3 completo en buffer.
        
        Args:
            text: Texto a convertir en audio
            lang: Código de idioma (ej: 'es', 'en')
            
        Returns:
            Audio MP3 en bytes
        """
        from gtts import gTTS

        start_time = time.time()

        try:
            # gTTS es síncrono, ejecutar en un thread para no bloquear el event loop
            def _generate():
                tts = gTTS(text=text, lang=lang)
                buffer = io.BytesIO()
                tts.write_to_fp(buffer)
                buffer.seek(0)
                return buffer.read()

            loop = asyncio.get_event_loop()
            audio_bytes = await loop.run_in_executor(None, _generate)

            elapsed = time.time() - start_time
            logger.info(
                f"[gTTS] Audio generado: {len(audio_bytes)} bytes, "
                f"lang={lang}, duración={elapsed:.2f}s"
            )
            return audio_bytes

        except Exception as e:
            logger.error(f"[gTTS] Error generando audio: {e}")
            raise

    async def generate_stream(self, text: str, lang: str = "es") -> AsyncGenerator[bytes, None]:
        """
        Genera audio y lo entrega como un solo chunk (simula streaming).
        
        Args:
            text: Texto a convertir
            lang: Código de idioma
            
        Yields:
            Audio MP3 completo como un único chunk
        """
        audio_bytes = await self.generate_audio(text, lang)
        yield audio_bytes


# =============================================================================
# SERVICIO TTS ORQUESTADOR
# =============================================================================

class TTSService:
    """
    Servicio orquestador de TTS con fallback automático.
    Intenta EdgeTTS primero, cae a gTTS si falla.
    """

    def __init__(self):
        self.edge_provider = EdgeTTSProvider()
        self.gtts_provider = GTTSProvider()

        # Métricas simples
        self.stats = {
            "edge": {"total": 0, "success": 0, "errors": 0},
            "gtts": {"total": 0, "success": 0, "errors": 0},
        }

    def _extract_lang_from_voice(self, voice: str) -> str:
        """Extrae el código de idioma de un nombre de voz (ej: 'es-CO-SalomeNeural' → 'es')."""
        if "-" in voice:
            return voice.split("-")[0]
        return "es"

    async def speak(
        self,
        text: str,
        voice: str = "es-MX-JorgeNeural",
        rate: str = "+20%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        provider: str = "auto"
    ) -> AsyncGenerator[bytes, None]:
        """
        Genera audio TTS con fallback automático.
        
        Args:
            text: Texto a convertir
            voice: Nombre de la voz
            rate: Velocidad del habla
            volume: Volumen
            pitch: Tono
            provider: 'auto', 'edge' o 'gtts'
            
        Yields:
            Chunks de audio MP3
        """
        # Limpiar texto de Markdown básico para mejorar la lectura
        clean_text = self._clean_text_for_speech(text)

        # Seleccionar proveedor
        if provider == "gtts":
            async for chunk in self._use_gtts(clean_text, voice):
                yield chunk
            return

        if provider == "edge":
            async for chunk in self._use_edge(clean_text, voice, rate, volume, pitch):
                yield chunk
            return

        # Modo auto: intentar edge primero, fallback a gtts
        if await self.edge_provider.is_available():
            try:
                async for chunk in self._use_edge(
                    clean_text, voice, rate, volume, pitch
                ):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"[TTSService] EdgeTTS falló, usando fallback gTTS: {e}")

        # Fallback a gTTS
        async for chunk in self._use_gtts(clean_text, voice):
            yield chunk

    async def _use_edge(
        self, text: str, voice: str, rate: str, volume: str, pitch: str
    ) -> AsyncGenerator[bytes, None]:
        """Usa EdgeTTS directamente con chunking para textos largos."""
        self.stats["edge"]["total"] += 1
        try:
            chunks = self._chunk_text(text, max_length=1500)
            for text_chunk in chunks:
                if not text_chunk.strip(): continue
                async for audio_chunk in self.edge_provider.generate_stream(text_chunk, voice, rate, volume, pitch):
                    yield audio_chunk
            self.stats["edge"]["success"] += 1
        except Exception as e:
            self.stats["edge"]["errors"] += 1
            raise

    async def _use_gtts(self, text: str, voice: str) -> AsyncGenerator[bytes, None]:
        """Usa gTTS como fallback."""
        self.stats["gtts"]["total"] += 1
        try:
            lang = self._extract_lang_from_voice(voice)
            async for chunk in self.gtts_provider.generate_stream(text, lang):
                yield chunk
            self.stats["gtts"]["success"] += 1
        except Exception as e:
            self.stats["gtts"]["errors"] += 1
            raise

    async def list_voices(self, locale_filter: str = "es") -> List[Dict[str, Any]]:
        """Lista las voces disponibles del proveedor edge-tts."""
        if await self.edge_provider.is_available():
            return await self.edge_provider.list_voices(locale_filter)
        return []

    def get_metrics(self) -> Dict[str, Any]:
        """Retorna métricas de uso del servicio TTS."""
        return {
            "providers": self.stats,
            "edge_available": self.edge_provider._available,
            "gtts_available": self.gtts_provider._available,
        }

    @staticmethod
    def _chunk_text(text: str, max_length: int = 1500) -> List[str]:
        """Divide el texto en fragmentos más pequeños para evitar límites y desconexiones de TTS."""
        import re
        paragraphs = text.split('\n')
        chunks = []
        current_chunk = ""
        
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            
            if len(current_chunk) + len(p) + 1 <= max_length:
                current_chunk += p + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                
                if len(p) > max_length:
                    sentences = re.split(r'(?<=[.!?])\s+', p)
                    for s in sentences:
                        if len(current_chunk) + len(s) + 1 <= max_length:
                            current_chunk += s + " "
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = s + " "
                else:
                    current_chunk = p + "\n"
                    
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    @staticmethod
    def _clean_text_for_speech(text: str) -> str:
        """
        Limpia texto Markdown para que se lea mejor en voz.
        Elimina sintaxis Markdown, URLs, bloques de código, etc.
        """
        import re

        # Eliminar bloques de código (```...```)
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Eliminar código inline (`...`)
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # Eliminar imágenes ![alt](url)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # Convertir enlaces [texto](url) → texto
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)

        # Eliminar encabezados Markdown (### texto → texto)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # Eliminar negrita/cursiva
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)

        # Eliminar listas markdown (- o * al inicio)
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)

        # Eliminar líneas horizontales
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

        # Eliminar URLs sueltas
        text = re.sub(r'https?://\S+', '', text)

        # Colapsar múltiples saltos de línea
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Limpiar espacios extras
        text = re.sub(r'  +', ' ', text)

        return text.strip()


# Instancia singleton del servicio
tts_service = TTSService()
