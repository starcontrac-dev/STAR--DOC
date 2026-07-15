import logging
import mimetypes
from typing import Optional

from fastapi import (
    APIRouter, UploadFile, File, Form, Query,
    HTTPException, BackgroundTasks, Depends, Request, Header
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.document_ipfs import DocumentIPFS
from app.models.user import User
from app.auth import get_current_user_optional, get_current_active_user
from app.core.limiter import limiter
from app.services.ipfs_service import IPFSService
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.crypto_engine import CryptoEngine, DocClassification
from app.services.webhook_service import WebhookService
from app.core.redis_client import redis_manager
import re

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IPFS & Web3"])

def is_valid_cid(cid: str) -> bool:
    """Valida la sintaxis estándar de CIDs de IPFS v0 y v1."""
    return bool(re.match(r"^(Qm[1-9a-km-zA-HJ-NP-Z]{44}|baf[a-z0-9]{56}|bafy[a-z0-9]{55})$", cid))

async def log_access_helper(
    cid: str,
    action: str,
    request: Request,
    session: AsyncSession,
    user: Optional[User] = None
):
    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    await IPFSIntegrationService.register_access_log(
        cid=cid,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        user_id=user.id if user else None,
        username=user.username if user else "Anonimo",
        session=session
    )

@router.get("/health", summary="Estado del nodo IPFS local")
async def ipfs_health():
    """Verifica que IPFS Desktop / Kubo esté activo y accesible."""
    import json
    # Intentar leer desde el caché en Redis
    try:
        pool = await redis_manager.get_pool(db=2)
        cached = await pool.get("ipfs:health")
        if cached:
            return json.loads(cached)
    except Exception as ex:
        logger.warning(f"Error al leer caché de IPFS health: {ex}")

    # Cache miss
    kubo = await IPFSService.check_kubo_health()
    
    ipns_pubsub = False
    if kubo.get("online", False):
        ipns_pubsub = await IPFSService.ensure_ipns_pubsub()

    result = {
        "kubo": kubo,
        "service": "ipfs_service",
        "version": "1.0.0",
        "ipns_pubsub_enabled": ipns_pubsub
    }

    # Guardar en Redis
    try:
        pool = await redis_manager.get_pool(db=2)
        await pool.setex("ipfs:health", 60, json.dumps(result))
    except Exception as ex:
        logger.warning(f"Error al guardar caché de IPFS health: {ex}")

    return result

@router.post("/upload", summary="Subir documento a IPFS")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    classification: str = Form("public"),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Sube un documento a IPFS vía nodo local Kubo.

    - **public**: Sin encriptación, CID verificable por cualquiera.
    - **confidential**: Encriptado con AES-256-GCM antes de subir.
    - **chain_of_custody**: Encriptado + audit trail forense.
    """
    try:
        doc_class = DocClassification(classification)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Clasificación inválida: '{classification}'. "
                   f"Opciones: public, confidential, chain_of_custody"
        )

    # Límite estricto de 100MB para prevenir desbordamientos de memoria RAM (OOM)
    max_bytes = 100 * 1024 * 1024
    file_data = await file.read(max_bytes + 1)
    if len(file_data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="El archivo excede el tamaño máximo permitido de 100MB."
        )

    if not file_data:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    file_size = len(file_data)
    mime = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"

    try:
        result = await IPFSService.secure_upload(
            file_name=file.filename or "documento",
            file_data=file_data,
            classification=doc_class,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    doc_record = DocumentIPFS(
        user_id=current_user.id if current_user else None,
        ipfs_cid=result["cid"],
        sha256_original=result["sha256_original"],
        classification=doc_class.value,
        is_encrypted=result["is_encrypted"],
        original_filename=file.filename or "documento",
        file_size_bytes=file_size,
        mime_type=mime,
        pinned_kubo=result.get("kubo") is not None,
        pinned_pinata=result.get("pinata") is not None,
        gateway_url=result.get("gateway_url"),
    )

    if result.get("encryption_key"):
        doc_record.encryption_key_encrypted = CryptoEngine.encrypt_document_key(
            result["encryption_key"], doc_record.user_id
        )

    session.add(doc_record)
    await session.commit()
    await session.refresh(doc_record)

    logger.info(f"Documento IPFS registrado: id={doc_record.id}, cid={result['cid']}")

    return {
        "id": doc_record.id,
        "cid": result["cid"],
        "sha256_original": result["sha256_original"],
        "classification": doc_class.value,
        "is_encrypted": result["is_encrypted"],
        "file_size_bytes": file_size,
        "original_filename": file.filename,
        "pinned_kubo": doc_record.pinned_kubo,
        "gateway_url": result.get("gateway_url"),
        "timestamp": result.get("timestamp"),
    }

@router.get("/verify/{cid}", summary="Verificar integridad de documento IPFS")
async def verify_document(
    cid: str,
    request: Request,
    sha256: str = Query(..., description="Hash SHA-256 esperado del documento original"),
    deep: bool = Query(False, description="Si es True, descarga y recalcula el hash. Si es False, usa caché de BD."),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Verifica la integridad y existencia de un documento en IPFS.
    - **Modo Rápido (deep=False)**: Valida contra los registros cacheados en PostgreSQL y el estado de pinning local en Kubo, sin descargar el archivo.
    - **Modo Profundo (deep=True)**: Descarga el contenido completo desde IPFS y recalcula el hash SHA-256 original (desencriptando si aplica).
    """
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)

    is_valid = False
    actual_hash = None
    verification_type = "CACHE"

    if not deep:
        if doc_record:
            actual_hash = doc_record.sha256_original
            is_valid = actual_hash == sha256
            
            try:
                pins = await IPFSService.list_pins_kubo()
                if cid not in pins:
                    logger.warning(f"CID {cid} registrado en BD pero ausente en pins locales de Kubo")
            except Exception as e:
                logger.warning(f"No se pudo consultar pins locales de Kubo para verificación rápida: {e}")
        else:
            deep = True

    if deep:
        verification_type = "DEEP_DOWNLOAD"
        try:
            content = await IPFSService.get_from_kubo(cid)
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"No se pudo recuperar el CID '{cid}' desde IPFS: {e}"
            )

        if doc_record and doc_record.is_encrypted and doc_record.encryption_key_encrypted:
            try:
                doc_key = CryptoEngine.decrypt_document_key(doc_record.encryption_key_encrypted, doc_record.user_id)
                decrypted_content = CryptoEngine.decrypt_from_envelope(content, doc_key)
                actual_hash = CryptoEngine.compute_sha256(decrypted_content)
            except Exception as e:
                logger.error(f"Error al desencriptar contenido para verificación profunda: {e}")
                actual_hash = CryptoEngine.compute_sha256(content)
        else:
            actual_hash = CryptoEngine.compute_sha256(content)

        is_valid = actual_hash == sha256

    await log_access_helper(cid, f"verify_{verification_type.lower()}", request, session, current_user)

    return {
        "cid": cid,
        "valid": is_valid,
        "expected_sha256": sha256,
        "actual_sha256": actual_hash,
        "verification_mode": verification_type,
        "verification": "INTEGRIDAD_CONFIRMADA" if is_valid else "INTEGRIDAD_FALLIDA",
    }

@router.get("/download/{cid}", summary="Descargar documento desde IPFS")
async def download_document(
    cid: str,
    request: Request,
    decrypt: bool = Query(True, description="Si es True y el archivo está encriptado, lo desencripta al vuelo (requiere login)."),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Descarga el contenido de un CID desde IPFS.
    - Para archivos públicos: Se descarga y entrega directamente en streaming de chunks.
    - Para archivos confidenciales: Si `decrypt=True` y el usuario está autenticado,
      se desencripta automáticamente al vuelo antes de la entrega (en memoria).
      En caso contrario (o si se pasa decrypt=False), se entrega el sobre encriptado raw por streaming.
    """
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)

    filename = f"{cid[:16]}.bin"
    mime = "application/octet-stream"
    action_log = "download"

    is_encrypted = doc_record and doc_record.is_encrypted

    if doc_record:
        filename = doc_record.original_filename
        mime = doc_record.mime_type or "application/octet-stream"

    background_tasks = BackgroundTasks()

    if is_encrypted and decrypt:
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="Debe iniciar sesión para descargar la versión desencriptada de este documento confidencial."
            )
        try:
            content = await IPFSService.get_from_kubo(cid)
            doc_key = CryptoEngine.decrypt_document_key(doc_record.encryption_key_encrypted, doc_record.user_id)
            content = CryptoEngine.decrypt_from_envelope(content, doc_key)
            action_log = "download_decrypted"
            await log_access_helper(cid, action_log, request, session, current_user)
            
            background_tasks.add_task(
                WebhookService.trigger_event,
                "download",
                {
                    "cid": cid,
                    "filename": filename,
                    "action": action_log,
                    "user_id": current_user.id if current_user else None
                }
            )
            
            return Response(
                content=content,
                media_type=mime,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-IPFS-CID": cid,
                },
                background=background_tasks
            )
        except Exception as e:
            logger.error(f"Error al desencriptar el sobre para descarga: {e}")
            raise HTTPException(
                status_code=500,
                detail="No se pudo desencriptar el documento. Llave corrupta o inválida."
            )
    else:
        if is_encrypted:
            filename = f"{filename}.enc"
            mime = "application/octet-stream"
            action_log = "download_encrypted"
        else:
            action_log = "download"

        await log_access_helper(cid, action_log, request, session, current_user)

        background_tasks.add_task(
            WebhookService.trigger_event,
            "download",
            {
                "cid": cid,
                "filename": filename,
                "action": action_log,
                "user_id": current_user.id if current_user else None
            }
        )

        async def stream_generator():
            async for chunk in IPFSService.stream_from_kubo(cid):
                yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-IPFS-CID": cid,
            },
            background=background_tasks
        )

@router.get("/download/{cid}/range", summary="Descargar rango de bytes (descarga parcial)")
async def download_document_range(
    cid: str,
    request: Request,
    offset: Optional[int] = Query(None, description="Byte de inicio"),
    length: Optional[int] = Query(None, description="Cantidad de bytes a leer"),
    range: Optional[str] = Header(None, description="Cabecera HTTP Range (ej. bytes=0-1023)"),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Descarga un rango parcial de bytes de un archivo público o encriptado crudo.
    Útil para visualizadores de PDFs (page-on-demand) o streaming de video.
    """
    req_offset = offset
    req_length = length
    
    if range and range.startswith("bytes="):
        try:
            parts = range.replace("bytes=", "").split("-")
            start = int(parts[0])
            req_offset = start
            if len(parts) > 1 and parts[1]:
                end = int(parts[1])
                req_length = (end - start) + 1
        except Exception:
            raise HTTPException(status_code=400, detail="Cabecera Range inválida")

    if req_offset is None:
        req_offset = 0

    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)
    is_encrypted = doc_record and doc_record.is_encrypted

    filename = f"{cid[:16]}.bin"
    mime = "application/octet-stream"
    
    if doc_record:
        filename = doc_record.original_filename
        mime = doc_record.mime_type or "application/octet-stream"
        
    if is_encrypted:
        filename = f"{filename}.enc"
        mime = "application/octet-stream"

    action_log = f"download_range_{req_offset}_{req_length}"
    await log_access_helper(cid, action_log, request, session, current_user)

    background_tasks = BackgroundTasks()
    background_tasks.add_task(
        WebhookService.trigger_event,
        "download",
        {
            "cid": cid,
            "filename": filename,
            "range": f"bytes {req_offset}-{req_offset + (req_length or 0) - 1 if req_length else 'EOF'}",
            "action": "range_download",
            "user_id": current_user.id if current_user else None
        }
    )

    async def range_stream():
        async for chunk in IPFSService.stream_from_kubo(cid, offset=req_offset, length=req_length):
            yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-IPFS-CID": cid,
        "Accept-Ranges": "bytes"
    }
    if req_length is not None:
        headers["Content-Length"] = str(req_length)
    if req_offset is not None:
        headers["Content-Range"] = f"bytes {req_offset}-{req_offset + (req_length or 1) - 1}/*"

    return StreamingResponse(
        range_stream(),
        status_code=206,
        media_type=mime,
        headers=headers,
        background=background_tasks
    )

@router.post("/decrypt/{cid}", summary="Desencriptar contenido de un documento para previsualización")
async def decrypt_document_endpoint(
    cid: str,
    body: dict = None,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Desencripta al vuelo un documento confidencial usando la clave resguardada en la BD
    y la sesión del usuario para mostrar su contenido plano en el visor de la Bóveda.
    """
    if not is_valid_cid(cid):
        raise HTTPException(status_code=400, detail="Formato de hash CID inválido.")

    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)
    if not doc_record:
        raise HTTPException(status_code=404, detail="Documento no registrado.")

    if not doc_record.is_encrypted:
        try:
            content = await IPFSService.get_from_kubo(cid)
            return {"success": True, "decrypted_content": content.decode("utf-8", errors="replace")}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error leyendo de IPFS: {e}")

    # Validar que el usuario logueado tenga permisos (propietario o administrador)
    is_admin = (
        getattr(current_user, 'role', None) == "admin" or
        current_user.username == "starcontract" or
        getattr(current_user, 'is_admin', False)
    )
    if current_user.id != doc_record.user_id and not is_admin:
        raise HTTPException(status_code=403, detail="No tiene permisos para desencriptar este archivo.")

    try:
        content = await IPFSService.get_from_kubo(cid)
        doc_key = CryptoEngine.decrypt_document_key(doc_record.encryption_key_encrypted, doc_record.user_id)
        decrypted_content = CryptoEngine.decrypt_from_envelope(content, doc_key)
        
        # Registrar acceso
        await IPFSIntegrationService.register_access_log(
            cid=cid,
            action="vault_decrypt_preview",
            ip_address=None,
            user_agent=None,
            user_id=current_user.id,
            username=current_user.username,
            session=session
        )

        return {
            "success": True,
            "decrypted_content": decrypted_content.decode("utf-8", errors="replace")
        }
    except Exception as e:
        logger.error(f"Error al desencriptar documento {cid}: {e}")
        raise HTTPException(status_code=500, detail="Fallo al desencriptar el documento.")
