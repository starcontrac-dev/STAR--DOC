import logging

import re
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, Response, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
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

@router.get("/pins", summary="Listar CIDs pineados en nodo local")
async def list_pins(current_user: User = Depends(is_admin_user)):
    """Lista todos los CIDs que están pineados en el nodo IPFS local."""
    try:
        pins = await IPFSService.list_pins_kubo()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar al nodo IPFS: {e}"
        )

    return {"count": len(pins), "pins": pins}

@router.get("/records", summary="Listar registros IPFS en base de datos")
async def list_records(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user),
):
    """Lista todos los documentos IPFS registrados en PostgreSQL."""
    records = await IPFSIntegrationService.list_documents_records(limit, offset, session)

    return {
        "count": len(records),
        "records": [
            {
                "id": r.id,
                "cid": r.ipfs_cid,
                "filename": r.original_filename,
                "classification": r.classification,
                "is_encrypted": r.is_encrypted,
                "file_size_bytes": r.file_size_bytes,
                "pinned_kubo": r.pinned_kubo,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }

@router.get("/repo/stats", summary="Estadísticas de almacenamiento IPFS")
async def repo_stats(current_user: User = Depends(is_admin_user)):
    """Obtiene estadísticas de almacenamiento del repositorio local IPFS de forma detallada."""
    try:
        stats = await IPFSService.get_repo_stats()
        return stats
    except Exception as e:
        logger.error(f"Error al obtener estadísticas del repo IPFS: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudieron obtener estadísticas del repo: {e}")

@router.post("/gc", summary="Ejecutar Garbage Collection en el nodo local")
async def trigger_gc(
    current_user: User = Depends(is_admin_user)
):
    """Ejecuta Garbage Collection en el nodo local Kubo para liberar espacio."""
    try:
        res = await IPFSService.run_gc()
        return res
    except Exception as e:
        logger.error(f"Error al ejecutar GC en Kubo: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo ejecutar GC: {e}")

@router.delete("/{cid}", summary="Despinear / archivar documento de IPFS")
async def unpin_document(
    cid: str,
    background_tasks: BackgroundTasks = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """Despinea un documento de Kubo local y actualiza su estado en base de datos."""
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)
    if not doc_record:
        raise HTTPException(status_code=404, detail="Documento no registrado en la base de datos.")

    try:
        await IPFSService.unpin_from_kubo(cid)
        await IPFSIntegrationService.unpin_document_record(cid, session)
        
        # Registrar acceso
        ip_address = None
        user_agent = None
        await IPFSIntegrationService.register_access_log(
            cid=cid,
            action="unpin",
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=current_user.id,
            username=current_user.username,
            session=session
        )

        if background_tasks:
            background_tasks.add_task(
                WebhookService.trigger_event,
                "archive",
                {
                    "cid": cid,
                    "filename": doc_record.original_filename,
                    "user_id": current_user.id
                }
            )
        
        return {
            "status": "success",
            "cid": cid,
            "detail": "Documento despineado localmente y archivado correctamente."
        }
    except Exception as e:
        logger.error(f"Error al despinear CID {cid}: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo despinear el documento de Kubo: {e}")

@router.post("/sync-pinata", summary="Forzar sincronización de un documento con Pinata")
async def sync_document_pinata(
    cid: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_user)
):
    """
    Intenta pinear en Pinata Cloud un documento que falló previamente o no se subió
    debido a la estrategia híbrida, para garantizar redundancia en la red.
    """
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)
    if not doc_record:
        raise HTTPException(status_code=404, detail="Documento no registrado en la base de datos.")

    try:
        logger.info(f"Sincronizando CID {cid} con Pinata para redundancia.")
        res = await IPFSService.pin_by_cid_pinata(cid, doc_record.original_filename)
        await IPFSIntegrationService.sync_pinata_record(cid, session)
        
        return {
            "status": "success",
            "cid": cid,
            "pinata_id": res.get("id"),
            "detail": "Documento sincronizado y pineado en Pinata exitosamente."
        }
    except Exception as e:
        logger.error(f"Error al sincronizar con Pinata para CID {cid}: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo sincronizar con Pinata: {e}")

@router.get("/export-car/{cid}", summary="Exportar DAG completo a archivo CAR")
async def export_dag_car(cid: str, current_user: User = Depends(is_admin_user)):
    """Exporta un CID y todo su árbol Merkle DAG en formato CAR."""
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")
    try:
        car_content = await IPFSService.dag_export(cid)
        return Response(
            content=car_content,
            media_type="application/vnd.ipld.car",
            headers={"Content-Disposition": f"attachment; filename={cid}.car"}
        )
    except Exception as e:
        logger.error(f"Error al exportar CAR para CID {cid}: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo exportar el CAR: {e}")

@router.post("/import-car", summary="Importar y pinear archivo CAR en Kubo")
async def import_dag_car(
    file: UploadFile = File(...),
    current_user: User = Depends(is_admin_user)
):
    """Importa un archivo CAR a Kubo local y pin-roots automático."""
    car_data = await file.read()
    try:
        res = await IPFSService.dag_import(car_data)
        return {
            "status": "success", 
            "roots": res.get("RootCids") or res.get("Roots"), 
            "detail": "Archivo CAR importado y anclado con éxito."
        }
    except Exception as e:
        logger.error(f"Error al importar archivo CAR: {e}")
        raise HTTPException(status_code=500, detail=f"No se pudo importar el CAR: {e}")
