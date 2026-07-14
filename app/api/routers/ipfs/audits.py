import logging
import os
import re
import mimetypes
import io
import zipfile
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import (
    APIRouter, UploadFile, File, Form, Query,
    HTTPException, BackgroundTasks, Depends, Request
)
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_session
from app.models.document_ipfs import DocumentIPFS
from app.models.user import User
from app.auth import get_current_user_optional, get_current_active_user
from app.services.ipfs_service import IPFSService
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.crypto_engine import CryptoEngine, DocClassification
from app.services.webhook_service import WebhookService
from app.core.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["IPFS & Web3"])

class PackAuditRequest(BaseModel):
    name: str
    document_ids: list[int]

async def log_access_helper(
    cid: str,
    action: str,
    request: Optional[Request],
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

@router.get("/certificate/{cid}", summary="Generar Certificado HTML de Evidencia")
async def get_html_certificate(
    cid: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Genera un documento HTML standalone con la prueba de existencia del archivo,
    sus huellas criptográficas SHA256 y enlaces a los gateways IPFS.
    """
    doc_record = await IPFSIntegrationService.get_document_by_cid(cid, session)
    if not doc_record:
        raise HTTPException(status_code=404, detail="Registro no encontrado para el CID especificado.")

    await log_access_helper(cid, "certificate_view", request, session, current_user)

    inbrowser_link = f"https://{cid}.ipfs.inbrowser.link/" if cid.startswith("baf") else f"https://ipfs.io/ipfs/{cid}"
    ipfs_link = f"https://ipfs.io/ipfs/{cid}"

    from datetime import timedelta
    created_at_local = (doc_record.created_at - timedelta(hours=5)) if doc_record.created_at else None
    created_at_str = created_at_local.strftime('%Y-%m-%d %H:%M:%S COT') if created_at_local else 'N/A'

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Certificado de Evidencia Blockchain - STAR-DOC</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; color: #333; line-height: 1.6; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); border-top: 5px solid #0056b3; }}
            .header {{ text-align: center; border-bottom: 2px solid #eee; padding-bottom: 20px; margin-bottom: 20px; }}
            .header h1 {{ color: #0056b3; margin: 0; }}
            .badge {{ display: inline-block; padding: 5px 10px; background: #28a745; color: white; border-radius: 20px; font-size: 0.85em; font-weight: bold; margin-top: 10px; }}
            .section-title {{ color: #0056b3; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-top: 30px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ padding: 12px 15px; border: 1px solid #ddd; text-align: left; }}
            th {{ background-color: #f8f9fa; font-weight: 600; width: 30%; }}
            .hash {{ font-family: 'Courier New', Courier, monospace; background: #f8f9fa; padding: 2px 5px; border-radius: 4px; word-break: break-all; }}
            .btn {{ display: inline-block; background: #0056b3; color: #fff; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; text-align: center; font-weight: bold; }}
            .btn:hover {{ background: #004494; }}
            .footer {{ text-align: center; margin-top: 40px; font-size: 0.85em; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Certificado de Evidencia Criptográfica</h1>
                <div class="badge">Autenticidad Verificada ✓</div>
            </div>
            
            <p>Este documento certifica que el archivo mencionado a continuación ha sido sellado de forma inmutable en la red descentralizada IPFS, garantizando su fecha de creación e integridad matemática.</p>
            
            <h2 class="section-title">Detalles del Documento</h2>
            <table>
                <tr><th>Nombre Original</th><td>{doc_record.original_filename}</td></tr>
                <tr><th>Tamaño</th><td>{doc_record.file_size_bytes} bytes</td></tr>
                <tr><th>Clasificación</th><td>{doc_record.classification.upper()}</td></tr>
                <tr><th>Fecha de Anclaje</th><td>{created_at_str}</td></tr>
            </table>

            <h2 class="section-title">Huellas Criptográficas</h2>
            <table>
                <tr><th>Hash IPFS (CID)</th><td class="hash">{cid}</td></tr>
                <tr><th>SHA-256 (Original)</th><td class="hash">{doc_record.sha256_original}</td></tr>
            </table>

            <h2 class="section-title">Enlaces de Verificación (Nodos Públicos)</h2>
            <p>Accede al documento directamente desde la red IPFS utilizando cualquiera de los siguientes gateways:</p>
            <ul>
                <li><a href="{inbrowser_link}" target="_blank">Gateway Inbrowser (Recomendado)</a></li>
                <li><a href="{ipfs_link}" target="_blank">Gateway Público (IPFS.io)</a></li>
            </ul>

            <div style="text-align: center;">
                <a href="{inbrowser_link}" class="btn" target="_blank">Ver Documento en la Web3</a>
            </div>

            <div class="footer">
                Generado automáticamente por STAR-DOC Security.<br>
                Este certificado HTML es independiente y puede ser guardado como evidencia legal.
            </div>
        </div>
    </body>
    </html> 
    """
    return HTMLResponse(content=html_content)

@router.post("/pack-audit", summary="Empaquetar documentos en un expediente IPFS")
async def pack_audit_endpoint(
    req: PackAuditRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Agrupa una lista de IDs de documentos en un único directorio IPFS (Merkle DAG),
    creando la estructura de carpetas en Kubo MFS y registrando la auditoría.
    """
    try:
        audit_record = await IPFSIntegrationService.pack_audit(
            audit_name=req.name,
            document_ids=req.document_ids,
            session=session
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "id": audit_record.id,
        "name": audit_record.name,
        "ipfs_cid": audit_record.ipfs_cid,
        "classification": audit_record.classification,
        "document_ids": audit_record.document_ids,
        "created_at": audit_record.created_at.isoformat(),
        "gateway_url": f"https://ipfs.io/ipfs/{audit_record.ipfs_cid}"
    }

@router.get("/audits", summary="Listar auditorías registradas")
async def list_audits(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """Lista todos los paquetes de auditoría registrados en la base de datos."""
    audits = await IPFSIntegrationService.list_audits_records(limit, offset, session)
    return {
        "count": len(audits),
        "audits": [
            {
                "id": a.id,
                "name": a.name,
                "ipfs_cid": a.ipfs_cid,
                "classification": a.classification,
                "document_ids": a.document_ids,
                "created_at": a.created_at.isoformat()
            }
            for a in audits
        ]
    }

@router.get("/audit/{id_or_cid}/logs", summary="Obtener cadena de custodia (logs de acceso)")
async def get_audit_logs(
    id_or_cid: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
):
    """
    Obtiene los registros de acceso e integridad (cadena de custodia) para un CID
    o para una auditoría específica (buscando logs de sus documentos constitutivos).
    """
    audit = await IPFSIntegrationService.get_audit_by_cid_or_id(id_or_cid, session)
    cids_to_query = []
    audit_name = None

    if audit:
        audit_name = audit.name
        cids_to_query.append(audit.ipfs_cid)
        if audit.document_ids:
            # Recuperar documentos y agregar CIDs
            for doc_id in audit.document_ids:
                doc = await IPFSIntegrationService.get_document_by_cid(str(doc_id), session)
                if doc:
                    cids_to_query.append(doc.ipfs_cid)
    else:
        # Intentar tratarlo como un CID individual de documento
        doc = await IPFSIntegrationService.get_document_by_cid(id_or_cid, session)
        if doc:
            cids_to_query.append(doc.ipfs_cid)
        else:
            cids_to_query.append(id_or_cid)

    if not cids_to_query:
        return {"audit_name": audit_name, "logs_count": 0, "logs": []}

    logs = await IPFSIntegrationService.get_access_logs(cids_to_query, session)

    return {
        "audit_name": audit_name,
        "logs_count": len(logs),
        "logs": [
            {
                "id": l.id,
                "ipfs_cid": l.ipfs_cid,
                "user_id": l.user_id,
                "username": l.username,
                "action": l.action,
                "ip_address": l.ip_address,
                "user_agent": l.user_agent,
                "accessed_at": l.accessed_at.isoformat()
            }
            for l in logs
        ]
    }

@router.get("/audit/{id_or_cid}", summary="Obtener detalles de una auditoría y sus documentos")
async def get_audit_details(
    id_or_cid: str,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Obtiene la información de una auditoría y la lista de todos los documentos
    asociados con sus respectivos metadatos criptográficos y de integridad.
    """
    audit = await IPFSIntegrationService.get_audit_by_cid_or_id(id_or_cid, session)
    if not audit:
        raise HTTPException(status_code=404, detail="Expediente de auditoría no encontrado.")

    documents = []
    if audit.document_ids:
        for doc_id in audit.document_ids:
            d = await IPFSIntegrationService.get_document_by_cid(str(doc_id), session)
            if d:
                documents.append({
                    "id": d.id,
                    "filename": d.original_filename,
                    "cid": d.ipfs_cid,
                    "sha256": d.sha256_original,
                    "classification": d.classification,
                    "size_bytes": d.file_size_bytes,
                    "pinned_kubo": d.pinned_kubo,
                    "pinned_pinata": d.pinned_pinata,
                    "created_at": d.created_at.isoformat() if d.created_at else None
                })

    return {
        "id": audit.id,
        "name": audit.name,
        "ipfs_cid": audit.ipfs_cid,
        "classification": audit.classification,
        "created_at": audit.created_at.isoformat(),
        "documents": documents
    }

@router.get("/download-pack/{cid}", summary="Descargar expediente IPFS completo en ZIP")
async def download_pack(
    cid: str,
    decrypt: bool = Query(True, description="Si es True, desencripta los documentos confidenciales en el ZIP (requiere login/permisos)"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Descarga un expediente completo de auditoría en un archivo ZIP.
    Incluye todos los documentos asociados y un certificado de auditoría en HTML.
    """
    audit = await IPFSIntegrationService.get_audit_by_cid_or_id(cid, session)
    if not audit:
        raise HTTPException(
            status_code=404,
            detail="Paquete de auditoría no encontrado con el CID especificado en la base de datos."
        )

    doc_ids = audit.document_ids or []
    if not doc_ids:
        raise HTTPException(status_code=400, detail="El expediente no contiene documentos registrados.")

    documents = []
    for doc_id in doc_ids:
        doc = await IPFSIntegrationService.get_document_by_cid(str(doc_id), session)
        if doc:
            documents.append(doc)

    zip_buffer = io.BytesIO()
    doc_meta_list = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for doc in documents:
            try:
                doc_content = await IPFSService.get_from_kubo(doc.ipfs_cid)
                filename = doc.original_filename
                decrypted_successfully = False
                
                if doc.is_encrypted:
                    if decrypt:
                        try:
                            doc_key = CryptoEngine.decrypt_document_key(doc.encryption_key_encrypted, doc.user_id)
                            doc_content = CryptoEngine.decrypt_from_envelope(doc_content, doc_key)
                            decrypted_successfully = True
                        except Exception as e:
                            logger.error(f"Fallo al desencriptar {doc.ipfs_cid}: {e}")
                            filename = f"{filename}.enc"
                    else:
                        filename = f"{filename}.enc"
                
                zip_file.writestr(filename, doc_content)
                
                doc_meta_list.append({
                    "id": doc.id,
                    "filename": filename,
                    "cid": doc.ipfs_cid,
                    "sha256": doc.sha256_original,
                    "size": doc.file_size_bytes,
                    "classification": doc.classification,
                    "decrypted": decrypted_successfully,
                    "created_at": doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "N/A"
                })
            except Exception as e:
                logger.error(f"Error al procesar documento {doc.ipfs_cid} para el ZIP: {e}")

        from datetime import timedelta
        current_time = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S COT")
        
        doc_rows = ""
        for d in doc_meta_list:
            status_badge = f'<span class="badge {d["classification"]}">{d["classification"].upper()}</span>'
            dec_status = "Desencriptado" if d["decrypted"] else ("Original (Público)" if d["classification"] == "public" else "Cifrado")
            doc_rows += f"""
            <tr>
                <td>{d['filename']}</td>
                <td class="mono">{d['cid']}</td>
                <td class="mono">{d['sha256']}</td>
                <td>{d['size']} B</td>
                <td>{status_badge}</td>
                <td>{dec_status}</td>
                <td>{d['created_at']}</td>
            </tr>
            """

        html_certificate = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Certificado de Auditoría Criptográfica - STAR-DOC</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #1e293b;
            background-color: #f8fafc;
            margin: 0;
            padding: 40px;
            line-height: 1.6;
        }}
        .certificate-container {{
            max-width: 1000px;
            margin: 0 auto;
            background: #ffffff;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            border-radius: 12px;
            padding: 40px;
            position: relative;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #0f172a;
            font-size: 24px;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .header p {{
            color: #64748b;
            margin: 5px 0 0 0;
        }}
        .meta-box {{
            background: #f1f5f9;
            border-left: 4px solid #3b82f6;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 30px;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }}
        .meta-item strong {{
            color: #475569;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
            font-size: 14px;
        }}
        th {{
            background-color: #f8fafc;
            color: #334155;
            font-weight: 600;
        }}
        .mono {{
            font-family: monospace;
            word-break: break-all;
            background: #f8fafc;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 12px;
        }}
        .badge {{
            padding: 3px 8px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge.public {{ background-color: #dcfce7; color: #15803d; }}
        .badge.confidential {{ background-color: #fee2e2; color: #b91c1c; }}
        .badge.chain_of_custody {{ background-color: #fef9c3; color: #a16207; }}
        .legal-footer {{
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
            margin-top: 40px;
            font-size: 13px;
            color: #64748b;
            text-align: justify;
        }}
        .signature-section {{
            margin-top: 40px;
            text-align: right;
        }}
        .stamp {{
            display: inline-block;
            border: 2px dashed #10b981;
            color: #10b981;
            padding: 10px 20px;
            font-weight: bold;
            text-transform: uppercase;
            border-radius: 4px;
            transform: rotate(-3deg);
        }}
    </style>
</head>
<body>
    <div class="certificate-container">
        <div class="header">
            <h1>Certificado de Custodia y Auditoría Criptográfica</h1>
            <p>Generado automáticamente por la Plataforma Segura STAR-DOC</p>
        </div>

        <div class="meta-box">
            <div class="meta-grid">
                <div class="meta-item">
                    <strong>Nombre del Expediente:</strong> {audit.name}
                </div>
                <div class="meta-item">
                    <strong>CID del Paquete (IPFS):</strong> <span class="mono">{cid}</span>
                </div>
                <div class="meta-item">
                    <strong>Fecha de Certificación:</strong> {current_time}
                </div>
                <div class="meta-item">
                    <strong>Operador de Certificación:</strong> STAR-DOC Engine v2.5
                </div>
            </div>
        </div>

        <h3>Documentos Incorporados</h3>
        <table>
            <thead>
                <tr>
                    <th>Nombre de Archivo</th>
                    <th>CID (IPFS)</th>
                    <th>Hash SHA-256 Original</th>
                    <th>Tamaño</th>
                    <th>Clasificación</th>
                    <th>Estado</th>
                    <th>Fecha de Subida</th>
                </tr>
            </thead>
            <tbody>
                {doc_rows}
            </tbody>
        </table>

        <div class="legal-footer">
            <p><strong>Fundamento Jurídico (República de Colombia):</strong> Este certificado digital y los documentos asociados a la firma criptográfica se expiden de conformidad con lo establecido en la <strong>Ley 527 de 1999</strong>, por medio de la cual se define y reglamenta el acceso y uso de los mensajes de datos, del comercio electrónico y de las firmas digitales, y se establecen las entidades de certificación. De acuerdo con el Artículo 6 (Escrito), Artículo 7 (Firma), Artículo 8 (Original) y Artículo 10 (Admisibilidad y fuerza probatoria de los mensajes de datos), los documentos vinculados y su hash SHA-256 gozan de plena validez jurídica, no repudio y eficacia probatoria equivalente a su contraparte en soporte físico, garantizando la integridad inalterable de la información contenida.</p>
        </div>

        <div class="signature-section">
            <div class="stamp">SELLADO CRIPTOGRÁFICO STAR-DOC</div>
        </div>
    </div>
</body>
</html>
"""
        zip_file.writestr("STAR-DOC-CERTIFICATE.html", html_certificate)

    zip_buffer.seek(0)
    
    await log_access_helper(cid, "download_pack_zip", request=None, session=session, user=current_user)

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="expediente_{cid[:8]}.zip"',
            "X-IPFS-CID": cid,
        }
    )

@router.post("/upload-folder", summary="Subir una carpeta de documentos a IPFS y crear expediente")
@limiter.limit("5/minute")
async def upload_folder_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    classification: str = Form("public"),
    folder_name: str = Form(None),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Sube múltiples documentos (como una carpeta o expediente) a IPFS,
    aplicando cifrado si corresponde, los registra en base de datos y los empaqueta
    automáticamente en un nuevo expediente (IPFSAudit).
    """
    try:
        doc_class = DocClassification(classification)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Clasificación inválida: '{classification}'. Opciones: public, confidential, chain_of_custody"
        )

    if not files:
        raise HTTPException(status_code=400, detail="No se recibieron archivos.")

    if not folder_name:
        first_file = files[0].filename or ""
        parts = [p for p in first_file.replace("\\", "/").split("/") if p]
        if len(parts) > 1:
            folder_name = parts[0]
        else:
            folder_name = f"expediente_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    uploaded_doc_ids = []
    
    for file in files:
        file_data = await file.read()
        if not file_data:
            continue
            
        file_size = len(file_data)
        clean_filename = os.path.basename(file.filename or "documento")
        mime = mimetypes.guess_type(clean_filename)[0] or "application/octet-stream"

        try:
            result = await IPFSService.secure_upload(
                file_name=clean_filename,
                file_data=file_data,
                classification=doc_class,
            )
        except Exception as e:
            logger.error(f"Error subiendo {clean_filename} en carga de carpeta: {e}")
            raise HTTPException(status_code=500, detail=f"Error al subir '{clean_filename}': {str(e)}")

        doc_record = DocumentIPFS(
            user_id=current_user.id,
            ipfs_cid=result["cid"],
            sha256_original=result["sha256_original"],
            classification=doc_class.value,
            is_encrypted=result["is_encrypted"],
            original_filename=clean_filename,
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
        
        uploaded_doc_ids.append(doc_record.id)

    if not uploaded_doc_ids:
        raise HTTPException(status_code=400, detail="No se pudo procesar ningún archivo de la carpeta.")

    try:
        audit_record = await IPFSIntegrationService.pack_audit(
            audit_name=folder_name,
            document_ids=uploaded_doc_ids,
            session=session
        )
    except Exception as e:
        logger.error(f"Error al empaquetar la carpeta en un expediente: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Carpeta subida, pero falló la creación del expediente criptográfico: {str(e)}"
        )

    return {
        "status": "success",
        "folder_name": folder_name,
        "audit_id": audit_record.id,
        "ipfs_cid": audit_record.ipfs_cid,
        "classification": audit_record.classification,
        "document_ids": audit_record.document_ids,
        "documents_count": len(uploaded_doc_ids),
        "created_at": audit_record.created_at.isoformat()
    }
