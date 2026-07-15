import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.ipns_key import IPNSKey
from app.models.user import User
from app.auth import get_current_active_user, is_admin_user
from app.services.ipfs_service import IPFSService
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IPFS & Web3"])

def is_valid_cid(cid: str) -> bool:
    """Valida la sintaxis estándar de CIDs de IPFS v0 y v1."""
    return bool(re.match(r"^(Qm[1-9a-km-zA-HJ-NP-Z]{44}|baf[a-z0-9]{56}|bafy[a-z0-9]{55})$", cid))

@router.post("/ipns/key", summary="Generar clave IPNS para versionado")
async def create_ipns_key(
    key_name: str = Query(..., description="Nombre de la clave para identificar el contrato"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """
    Genera una nueva clave criptográfica en el nodo IPFS para publicar versionamiento
    y la persiste en la base de datos PostgreSQL.
    """
    try:
        res = await IPFSService.ipns_create_key(key_name)
        ipns_addr = res.get("Id")
        
        await IPFSIntegrationService.save_ipns_key(
            key_name=key_name,
            ipns_id=ipns_addr,
            cid=None,
            session=session
        )
        
        return {
            "status": "success",
            "key_name": key_name,
            "ipns_address": ipns_addr,
            "detail": f"Clave IPNS '{key_name}' generada y guardada exitosamente en base de datos."
        }
    except Exception as e:
        logger.error(f"Error al generar clave IPNS: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo crear la clave IPNS: {e}")

@router.post("/ipns/publish", summary="Publicar nueva versión de un contrato bajo clave IPNS")
async def publish_ipns(
    key_name: str = Query(..., description="Nombre de la clave IPNS generada previamente"),
    cid: str = Query(..., description="El CID inmutable del nuevo contrato/documento"),
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """
    Apunta el nombre IPNS mutable (representado por la clave) al CID inmutable especificado.
    Registra el historial y actualiza el CID actual de la clave IPNS en PostgreSQL.
    """
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    try:
        res = await IPFSService.ipns_publish(cid, key_name)
        ipns_name = res.get("Name")
        
        await IPFSIntegrationService.save_ipns_key(
            key_name=key_name,
            ipns_id=ipns_name,
            cid=cid,
            session=session,
            user_id=current_user.id
        )
            
        if background_tasks:
            background_tasks.add_task(
                WebhookService.trigger_event,
                "publish_ipns",
                {
                    "key_name": key_name,
                    "ipns_address": ipns_name,
                    "cid": cid,
                    "user_id": current_user.id
                }
            )
 
        return {
            "status": "published",
            "ipns_name": ipns_name,
            "target_cid": cid,
            "detail": f"Contrato publicado en IPNS mutable exitosamente."
        }
    except Exception as e:
        logger.error(f"Error al publicar en IPNS: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo publicar en IPNS: {e}")

@router.post("/ipns/republish-all", summary="Forzar republicación manual de todas las claves IPNS")
async def force_republish_all_ipns(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """
    Fuerza la republicación manual inmediata en Kubo de todas las claves IPNS activas en la BD.
    """
    from app.services.ipns_republisher_service import republish_all_ipns_keys
    try:
        count = await republish_all_ipns_keys(session)
        return {
            "status": "success",
            "republished_count": count,
            "detail": f"Se relanzó la republicación para {count} claves IPNS activas."
        }
    except Exception as e:
        logger.error(f"Error en republicación manual de IPNS: {e}")
        raise HTTPException(status_code=500, detail=f"Fallo al republicar claves IPNS: {e}")

@router.get("/ipns/resolve", summary="Resolver un nombre IPNS a su CID inmutable actual")
async def resolve_ipns(
    ipns_name: str = Query(..., description="El identificador de la clave IPNS (comienza por k51... o el PeerID)")
):
    """
    Resuelve el puntero IPNS mutable para obtener el CID inmutable de la versión actual del contrato.
    """
    try:
        target_path = await IPFSService.ipns_resolve(ipns_name)
        cid = target_path.replace("/ipfs/", "") if target_path.startswith("/ipfs/") else target_path
        return {
            "resolved": True,
            "ipns_name": ipns_name,
            "current_cid": cid,
            "gateway_url": IPFSService.get_gateway_url(cid)
        }
    except Exception as e:
        logger.error(f"Error al resolver IPNS: {e}")
        raise HTTPException(status_code=404, detail=f"No se pudo resolver el nombre IPNS: {e}")

@router.get("/ipns/keys", summary="Listar claves IPNS registradas en BD")
async def list_ipns_keys(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """Lista todas las claves IPNS registradas en la base de datos PostgreSQL."""
    try:
        keys = await IPFSIntegrationService.list_ipns_keys(session)
        return keys
    except Exception as e:
        logger.error(f"Error al listar claves IPNS de BD: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo listar claves IPNS: {e}")

@router.get("/ipns/history/{key_name}", summary="Obtener historial de versiones de una clave IPNS")
async def get_ipns_history(
    key_name: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtiene la bitácora completa de versiones históricas (CIDs publicados) 
    para una clave mutable de IPNS determinada.
    """
    db_key = await IPFSIntegrationService.get_ipns_key(key_name, session)
    if not db_key:
        raise HTTPException(status_code=404, detail="Clave IPNS no encontrada en el sistema.")

    from sqlmodel import select
    from app.models.ipns_version_history import IPNSVersionHistory
    stmt = select(IPNSVersionHistory).where(IPNSVersionHistory.ipns_key_id == db_key.id).order_by(IPNSVersionHistory.published_at.desc())
    res = await session.execute(stmt)
    history = res.scalars().all()
    
    return {
        "key_name": key_name,
        "ipns_id": db_key.ipns_id,
        "history": [
            {
                "id": h.id,
                "cid": h.cid,
                "published_at": h.published_at.isoformat(),
                "user_id": h.user_id
            }
            for h in history
        ]
    }
