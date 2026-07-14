import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_session
from app.models.user import User
from app.auth import get_current_active_user, is_admin_user
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.crypto_engine import CryptoEngine

logger = logging.getLogger(__name__)

import socket
import ipaddress
from urllib.parse import urlparse
from app.core.config import settings

def is_safe_url(url: str, allow_private: bool = False) -> bool:
    """Verifica si una URL es segura para evitar ataques SSRF."""
    if allow_private:
        return True
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        
        # Bloquear localhost explícito
        if host.lower() == "localhost":
            return False
            
        # Intentar resolver DNS a IPs
        addr_info = socket.getaddrinfo(host, None)
        for item in addr_info:
            ip_str = item[4][0]
            # Convertir a objeto ip_address (soporta IPv4 e IPv6)
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

router = APIRouter(tags=["IPFS & Web3"])

class WebhookCreate(BaseModel):
    name: Optional[str] = None
    url: str
    secret: Optional[str] = None
    events: List[str]  # ej. ["upload", "download"]

@router.post("/webhooks", summary="Crear suscripción a Webhook")
async def create_webhook(
    data: WebhookCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """Crea una nueva suscripción a webhooks para recibir notificaciones automáticas."""
    if not (data.url.startswith("http://") or data.url.startswith("https://")):
        raise HTTPException(status_code=400, detail="La URL de destino debe comenzar con http:// o https://")

    if not is_safe_url(data.url, allow_private=settings.ALLOW_PRIVATE_WEBHOOKS):
        raise HTTPException(
            status_code=400, 
            detail="La URL de destino no es permitida (debe ser una dirección IP pública y no loopback/privada para evitar ataques SSRF)."
        )

    name = data.name or f"webhook_{CryptoEngine.compute_sha256(data.url.encode())[:8]}"
    secret = data.secret or CryptoEngine.compute_sha256(data.url.encode())[:16]

    sub = await IPFSIntegrationService.create_webhook_subscription(
        name=name,
        url=data.url,
        secret=secret,
        events=data.events,
        session=session
    )
    
    return {
        "status": "success",
        "id": sub.id,
        "url": sub.url,
        "events": sub.events,
        "secret": sub.secret,
        "detail": "Suscripción a Webhook registrada exitosamente."
    }

@router.get("/webhooks", summary="Listar suscripciones a Webhooks")
async def list_webhooks(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """Lista todas las suscripciones a Webhooks activas."""
    webhooks = await IPFSIntegrationService.list_webhooks(session)
    return webhooks

@router.delete("/webhooks/{webhook_id}", summary="Eliminar suscripción a Webhook")
async def delete_webhook(
    webhook_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """Elimina una suscripción a Webhook existente."""
    success = await IPFSIntegrationService.delete_webhook_subscription(webhook_id, session)
    if not success:
        raise HTTPException(status_code=404, detail="Suscripción a Webhook no encontrada.")
        
    return {
        "status": "success",
        "detail": "Suscripción a Webhook eliminada exitosamente."
    }
