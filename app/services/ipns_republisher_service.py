import logging
from datetime import datetime
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ipns_key import IPNSKey
from app.services.ipfs_service import IPFSService

logger = logging.getLogger(__name__)

async def republish_all_ipns_keys(session: AsyncSession) -> dict:
    """
    Recorre todas las claves IPNS activas registradas en la base de datos
    que tengan un CID asignado, y fuerza su republicación en Kubo.
    """
    stmt = select(IPNSKey).where(IPNSKey.is_active == True).where(IPNSKey.current_cid != None)
    result = await session.execute(stmt)
    keys = result.scalars().all()
    
    success_count = 0
    fail_count = 0
    details = []
    
    for key in keys:
        try:
            logger.info(f"Republicando IPNS mutable: clave={key.key_name}, cid={key.current_cid}")
            await IPFSService.ipns_publish(key.current_cid, key.key_name)
            key.last_republished_at = datetime.utcnow()
            session.add(key)
            success_count += 1
            details.append({"key_name": key.key_name, "status": "success"})
        except Exception as e:
            logger.error(f"Error republicando clave IPNS '{key.key_name}': {e}")
            fail_count += 1
            details.append({"key_name": key.key_name, "status": "failed", "error": str(e)})
            
    if success_count > 0 or fail_count > 0:
        await session.commit()
        
    return {
        "success_count": success_count,
        "fail_count": fail_count,
        "details": details
    }
