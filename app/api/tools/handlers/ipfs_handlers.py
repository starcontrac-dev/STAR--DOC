"""
Manejadores para las herramientas de IPFS de la IA.
Permiten a la IA certificar documentos y verificar integridad criptográfica.
"""

import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.tools.registry import register_tool
from app.models.document_ipfs import DocumentIPFS
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.ipfs_service import IPFSService
from app.services.crypto_engine import DocClassification

logger = logging.getLogger(__name__)

@register_tool("certificar_ipfs")
async def certificar_ipfs(args: dict, session: AsyncSession, username: str) -> dict:
    """
    Herramienta para certificar un archivo en IPFS.
    """
    filename = args.get("filename")
    classification = args.get("classification", "public")

    if not filename:
        return {"error": "Falta el nombre del archivo (filename)."}

    # Construir ruta al archivo en la carpeta output
    from app.core.config import settings
    file_path = os.path.join(settings.OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        return {"error": f"El archivo '{filename}' no existe en el sistema local."}

    try:
        doc_class = DocClassification(classification)
    except ValueError:
        return {"error": f"Clasificación inválida: '{classification}'."}

    try:
        doc_record = await IPFSIntegrationService.anchor_and_stamp(
            file_path=file_path,
            classification=doc_class,
            session=session
        )
        
        return {
            "status": "success",
            "message": "Archivo certificado y anclado en IPFS exitosamente.",
            "ipfs_cid": doc_record.ipfs_cid,
            "sha256": doc_record.sha256_original,
            "gateway_url": doc_record.gateway_url,
            "certificate_url": f"/api/ipfs/certificate/{doc_record.ipfs_cid}" # link local
        }
    except Exception as e:
        logger.error(f"Error certificando en IPFS: {e}")
        return {"error": str(e)}


@register_tool("verificar_documento")
async def verificar_documento(args: dict, session: AsyncSession, username: str) -> dict:
    """
    Verifica un documento usando su CID y opcionalmente su hash SHA-256 esperado.
    """
    cid = args.get("cid")
    expected_sha256 = args.get("sha256")

    if not cid:
        return {"error": "Falta el CID del documento a verificar."}

    try:
        content = await IPFSService.get_from_kubo(cid)
    except Exception as e:
        return {"error": f"No se pudo recuperar el documento de IPFS (CID: {cid}). Error: {e}"}

    from app.services.crypto_engine import CryptoEngine
    actual_hash = CryptoEngine.compute_sha256(content)
    
    result = {
        "cid": cid,
        "actual_sha256": actual_hash,
        "size_bytes": len(content)
    }

    if expected_sha256:
        is_valid = (actual_hash == expected_sha256)
        result["expected_sha256"] = expected_sha256
        result["is_valid"] = is_valid
        result["message"] = "Integridad CONFIRMADA" if is_valid else "Integridad FALLIDA"
    else:
        result["message"] = "Documento recuperado correctamente (no se proporcionó hash para comparar)."
        
    return result


@register_tool("empaquetar_auditoria")
async def empaquetar_auditoria(args: dict, session: AsyncSession, username: str) -> dict:
    """
    Agrupa múltiples documentos previamente certificados en un expediente/directorio IPFS (Merkle DAG).
    """
    name = args.get("name")
    document_ids = args.get("document_ids")

    if not name:
        return {"error": "Falta el nombre (name) del expediente."}
    if not document_ids or not isinstance(document_ids, list):
        return {"error": "Falta la lista de IDs de documentos (document_ids) a incluir."}

    try:
        audit_record = await IPFSIntegrationService.pack_audit(
            audit_name=name,
            document_ids=document_ids,
            session=session
        )
        return {
            "status": "success",
            "message": "Auditoría empaquetada exitosamente en IPFS.",
            "ipfs_cid": audit_record.ipfs_cid,
            "classification": audit_record.classification,
            "document_ids": audit_record.document_ids,
            "created_at": audit_record.created_at.isoformat(),
            "gateway_url": f"https://ipfs.io/ipfs/{audit_record.ipfs_cid}"
        }
    except Exception as e:
        logger.error(f"Error empaquetando auditoría en IPFS: {e}")
        return {"error": str(e)}

