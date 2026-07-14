import hmac
import hashlib
import json
import logging
from datetime import datetime
import httpx
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.webhook_subscription import WebhookSubscription
from app.database import async_session_maker

logger = logging.getLogger(__name__)

class WebhookService:
    @staticmethod
    async def trigger_event(event_name: str, payload: dict):
        """
        Dispara un evento de webhook en segundo plano.
        """
        try:
            async with async_session_maker() as session:
                stmt = select(WebhookSubscription).where(WebhookSubscription.is_active == True)
                result = await session.execute(stmt)
                subs = result.scalars().all()
                
                # Filtrar suscripciones que estén registradas para este evento específico
                active_subs = [s for s in subs if event_name in s.events]
                if not active_subs:
                    return
                
                # Despachar cada webhook de forma asíncrona
                import asyncio
                tasks = [WebhookService._dispatch(sub, event_name, payload) for sub in active_subs]
                await asyncio.gather(*tasks)
                
                # Actualizar last_triggered_at
                for sub in active_subs:
                    sub.last_triggered_at = datetime.utcnow()
                    session.add(sub)
                await session.commit()
        except Exception as e:
            logger.error(f"Error en trigger_event para '{event_name}': {e}")

    @staticmethod
    async def _dispatch(sub: WebhookSubscription, event: str, payload: dict):
        """
        Envía el payload firmado al endpoint del webhook.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Star-Doc-Webhooks/1.0",
            "X-StarDoc-Event": event
        }
        
        full_payload = {
            "event": event,
            "timestamp": datetime.utcnow().isoformat(),
            "data": payload
        }
        
        body_bytes = json.dumps(full_payload).encode("utf-8")
        
        if sub.secret:
            # Calcular firma HMAC-SHA256
            signature = hmac.new(
                sub.secret.encode("utf-8"),
                body_bytes,
                hashlib.sha256
            ).hexdigest()
            headers["X-StarDoc-Signature"] = signature
            
        # Validar SSRF antes de realizar la petición de red
        import socket
        import ipaddress
        from urllib.parse import urlparse
        from app.core.config import settings

        def is_safe_url(url: str) -> bool:
            if settings.ALLOW_PRIVATE_WEBHOOKS:
                return True
            try:
                parsed = urlparse(url)
                host = parsed.hostname
                if not host:
                    return False
                if host.lower() == "localhost":
                    return False
                addr_info = socket.getaddrinfo(host, None)
                for item in addr_info:
                    ip_str = item[4][0]
                    ip_obj = ipaddress.ip_address(ip_str)
                    if (ip_obj.is_private or 
                        ip_obj.is_loopback or 
                        ip_obj.is_reserved or 
                        ip_obj.is_unspecified or
                        ip_obj.is_multicast):
                        return False
                return True
            except Exception:
                return False

        if not is_safe_url(sub.url):
            logger.error(f"Despacho cancelado: La URL del webhook '{sub.url}' no es segura (SSRF detectado).")
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(sub.url, headers=headers, content=body_bytes)
                if resp.status_code >= 400:
                    logger.warning(f"Webhook '{sub.name}' respondió con status {resp.status_code} para evento '{event}'")
                else:
                    logger.info(f"Webhook '{sub.name}' enviado exitosamente para evento '{event}'")
        except Exception as e:
            logger.error(f"Error despachando webhook '{sub.name}' a '{sub.url}': {e}")
