"""
Servicio para la generación de enlaces de reunión y tokens JWT para Jitsi Meet.
"""
import time
import logging
from typing import Dict, Any, Optional
from jose import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

class JitsiService:
    @staticmethod
    def generate_meeting_url(
        room_name: str,
        user_name: str,
        user_email: str,
        is_moderator: bool = False
    ) -> Dict[str, Any]:
        """
        Genera la URL de la reunión y el token JWT de Jitsi si está configurado.
        Si JITSI_USE_JWT es False, genera un enlace a la sala pública.
        """
        domain = settings.JITSI_DOMAIN
        room_clean = room_name.replace(" ", "_").replace("/", "_")
        
        # Enlace base
        base_url = f"https://{domain}/{room_clean}"
        token = None

        if settings.JITSI_USE_JWT:
            if not settings.JITSI_APP_ID or not settings.JITSI_SECRET:
                logger.error("Jitsi JWT está habilitado pero JITSI_APP_ID o JITSI_SECRET no están configurados.")
                # Fallback a sala pública en desarrollo
            else:
                try:
                    token = JitsiService.generate_jwt_token(
                        room_name=room_clean,
                        user_name=user_name,
                        user_email=user_email,
                        is_moderator=is_moderator
                    )
                    base_url = f"https://{domain}/{room_clean}?jwt={token}"
                except Exception as e:
                    logger.error(f"Error generando token JWT para Jitsi: {e}", exc_info=True)

        return {
            "room_name": room_clean,
            "domain": domain,
            "url": base_url,
            "jwt_token": token
        }

    @staticmethod
    def generate_jwt_token(
        room_name: str,
        user_name: str,
        user_email: str,
        is_moderator: bool = False
    ) -> str:
        """
        Genera un JWT firmado para Jitsi Meet de acuerdo con los claims estándar de Prosody.
        """
        now = int(time.time())
        # Expiración: 1 hora a partir de ahora
        exp = now + 3600

        payload = {
            "aud": "jitsi",
            "iss": settings.JITSI_APP_ID,
            "sub": settings.JITSI_DOMAIN,
            "room": room_name,
            "iat": now,
            "exp": exp,
            "context": {
                "user": {
                    "name": user_name,
                    "email": user_email,
                    "moderator": "true" if is_moderator else "false"
                },
                "features": {
                    "recording": "true" if is_moderator else "false",
                    "livestreaming": "false",
                    "transcription": "true"
                }
            }
        }

        # Firmar usando HS256
        token = jwt.encode(payload, settings.JITSI_SECRET, algorithm="HS256")
        return token
