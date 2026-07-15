"""Router para generación de documentos (单个 y batch)."""
import os
import io
import uuid
import tempfile
import zipfile
import shutil
import logging
from typing import Optional

import polars as pl
import jinja2
from docxtpl import DocxTemplate
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import asyncio

from app.auth import (
    get_current_active_user,
    get_creds_for_user,
    create_file_download_token,
    verify_file_download_token,
    get_current_user_optional,
    verify_public_download_token
)
from app.models.user import User
from app.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.document_service import internal_generate_document
from app.services.email_service import send_email_with_gmail
from app.core.config import settings
from app.core.limiter import limiter
from app.core.utils import get_base_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Automation"])


@router.post("/generate-document")
@limiter.limit("15/minute")
async def generate_document(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Genera un documento单个 a partir de un template y contexto."""
    form_data = await request.form()
    form_dict = dict(form_data)

    template_content = None
    template_filename = ""
    google_doc_id = form_dict.pop('google_doc_id', None)

    # 1. Resolver Template
    if google_doc_id:
        creds = await get_creds_for_user(current_user, session)
        if not creds:
            raise HTTPException(400, "Google no conectado.")
        try:
            drive_service = build('drive', 'v3', credentials=creds)
            meta = await asyncio.to_thread(
                lambda: drive_service.files().get(fileId=google_doc_id, fields='name').execute()
            )
            template_filename = meta['name'] + ".docx"
            template_content = await asyncio.to_thread(
                lambda: drive_service.files().export_media(
                    fileId=google_doc_id,
                    mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ).execute()
            )
        except HttpError as e:
            logger.error(f"Error Drive: {e}")
            raise HTTPException(500, f"Error Drive: {e}")
    else:
        template_name = form_dict.pop('template_name', None)
        if not template_name:
            raise HTTPException(400, "No se especificó plantilla.")
        template_filename = template_name

    convert_flag = form_dict.pop('convert_pdf', None)
    output_format = form_dict.pop('output_format', 'docx')
    anchor_ipfs = form_dict.pop('anchor_ipfs', 'false').lower() == 'true'
    signature_workflow_enabled = form_dict.pop('signature_workflow_enabled', 'false').lower() == 'true'
    classification = form_dict.pop('classification', 'public')
    
    # Si la firma electrónica está activa, evitamos el sellado IPFS inicial sin firmar
    if signature_workflow_enabled:
        anchor_ipfs = False
        
    context = form_dict  # Remainder is context

    try:
        output_filename = await internal_generate_document(
            template_filename=template_filename,
            context=context,
            output_format=output_format,
            convert_pdf=bool(convert_flag),
            template_content=template_content,
            anchor_ipfs=anchor_ipfs,
            classification=classification,
            user_id=current_user.id
        )

        # Buscar información de IPFS si se solicitó anclaje
        ipfs_data = None
        if anchor_ipfs:
            from sqlmodel import select
            from app.models.document_ipfs import DocumentIPFS
            stmt = select(DocumentIPFS).where(DocumentIPFS.original_filename == output_filename).order_by(DocumentIPFS.created_at.desc())
            res = await session.execute(stmt)
            doc_ipfs = res.scalar_one_or_none()
            if doc_ipfs:
                ipfs_data = {
                    "cid": doc_ipfs.ipfs_cid,
                    "classification": doc_ipfs.classification,
                    "is_encrypted": doc_ipfs.is_encrypted,
                    "gateway_url": doc_ipfs.gateway_url,
                    "sha256_original": doc_ipfs.sha256_original
                }

        # --- Enviar Notificaciones de Sistema (Email 2026) ---
        from app.services.email import EmailService as SystemEmailService
        token = create_file_download_token(output_filename, current_user.id)
        base_url = get_base_url(request)
        download_url = f"{base_url}/files/{output_filename}?token={token}" # Endpoint público de descarga en Star-Doc
        
        # Alerta al abogado creador
        asyncio.create_task(
            SystemEmailService.send_document_generated_alert(
                recipient_email=current_user.email,
                document_name=output_filename,
                download_url=download_url
            )
        )
        
        # Alerta al cliente si se especificó su correo en el contexto
        client_email = context.get('client_email') or context.get('email') or context.get('lead_email')
        if client_email and client_email != current_user.email:
            asyncio.create_task(
                SystemEmailService.send_document_generated_alert(
                    recipient_email=client_email,
                    document_name=output_filename,
                    download_url=download_url
                )
            )

        # Email (si está configurado por el flujo legacy con Gmail OAuth)
        send_email_flag = context.pop('send_email', None)
        if send_email_flag:
            recipient_template = context.pop('recipient_email_template', '')
            subject_template = context.pop('email_subject_template', f"Documento: {output_filename}")
            body_template = context.pop('email_body_template', "Adjunto documento.")

            try:
                email_ctx = context.copy()
                recipient_email = jinja2.Template(recipient_template).render(email_ctx)
                email_subject = jinja2.Template(subject_template).render(email_ctx)
                email_body = jinja2.Template(body_template).render(email_ctx)
            except Exception as e:
                raise HTTPException(400, f"Error template email: {e}")

            if not recipient_email:
                raise HTTPException(400, "Email destinatario vacío.")

            final_path = os.path.join(settings.OUTPUT_DIR, output_filename)
            if not os.path.exists(final_path):
                raise HTTPException(500, "Archivo generado perdido.")

            creds = await get_creds_for_user(current_user, session)
            if not creds:
                raise HTTPException(400, "Google no conectado para email.")

            await send_email_with_gmail(creds, recipient_email, email_subject, email_body, final_path)
            token = create_file_download_token(output_filename, current_user.id)
            return {
                "success": True,
                "download_url": f"/files/{output_filename}?token={token}",
                "filename": output_filename,
                "email_sent_to": recipient_email,
                "ipfs": ipfs_data
            }

        token = create_file_download_token(output_filename, current_user.id)
        return {
            "success": True,
            "download_url": f"/files/{output_filename}?token={token}",
            "filename": output_filename,
            "ipfs": ipfs_data
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error generación: {e}")
        raise HTTPException(500, f"Error generación: {e}")


@router.post("/generate-batch")
@limiter.limit("5/minute")
async def generate_batch(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Generación en lote de documentos."""
    form_data = await request.form()

    send_email_flag = form_data.get('send_email')
    recipient_email_col = form_data.get('recipient_email_column')
    subject_tmpl_str = form_data.get('email_subject_template', "Doc: {{filename}}")
    body_tmpl_str = form_data.get('email_body_template', "Adjunto doc.")

    creds = None
    if send_email_flag:
        if not recipient_email_col:
            raise HTTPException(400, "Falta columna email.")
        creds = await get_creds_for_user(current_user, session)
        if not creds:
            raise HTTPException(400, "Google no conectado.")

    # Template
    tmpl_type = form_data.get('templateSourceType')
    tmpl_content = None
    tmpl_filename = ""
    template_content_str = ""  # for MD

    if tmpl_type == 'file':
        f = form_data.get('template_file')
        if not f:
            raise HTTPException(400, "Falta archivo plantilla.")
        tmpl_filename = f.filename
        if tmpl_filename.endswith('.md'):
            template_content_str = (await f.read()).decode('utf-8')
        else:
            tmpl_content = await f.read()
    elif tmpl_type == 'google_doc':
        doc_id = form_data.get('google_doc_id')
        if not doc_id:
            raise HTTPException(400, "Falta Doc ID.")
        creds_doc = await get_creds_for_user(current_user, session)
        if not creds_doc:
            raise HTTPException(400, "Google no conectado.")
        try:
            drv = build('drive', 'v3', credentials=creds_doc)
            meta = await asyncio.to_thread(
                lambda: drv.files().get(fileId=doc_id, fields='name').execute()
            )
            tmpl_filename = meta['name'] + ".docx"
            tmpl_content = await asyncio.to_thread(
                lambda: drv.files().export_media(
                    fileId=doc_id,
                    mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ).execute()
            )
        except HttpError as e:
            logger.error(f"Error Drive: {e}")
            raise HTTPException(500, f"Error Drive: {e}")

    # Data Source
    data_type = form_data.get('dataSourceType')
    contexts = []
    if data_type == 'file':
        df_file = form_data.get('data_file')
        if not df_file:
            raise HTTPException(400, "Falta archivo datos.")
        content = await df_file.read()
        f_io = io.BytesIO(content)
        if df_file.filename.endswith('.csv'):
            df = pl.read_csv(f_io)
        else:
            df = pl.read_excel(f_io, engine="calamine")
        contexts = df.to_dicts()
    elif data_type == 'google_sheet':
        sid = form_data.get('google_sheet_id')
        if not sid:
            raise HTTPException(400, "Falta Sheet ID.")
        creds_sheet = await get_creds_for_user(current_user, session)
        if not creds_sheet:
            raise HTTPException(400, "Google no conectado.")
        try:
            sht = build('sheets', 'v4', credentials=creds_sheet)
            res = await asyncio.to_thread(
                lambda: sht.spreadsheets().values().get(spreadsheetId=sid, range='A1:ZZ').execute()
            )
            vals = res.get('values', [])
            if len(vals) < 2:
                raise HTTPException(400, "Sheet sin datos.")
            headers, rows = vals[0], vals[1:]
            contexts = [dict(zip(headers, row)) for row in rows]
        except HttpError as e:
            logger.error(f"Error Sheets: {e}")
            raise HTTPException(500, f"Error Sheets: {e}")

    # Process
    base_name = tmpl_filename.rsplit('.', 1)[0]
    zip_name = f"{base_name}_lote_{uuid.uuid4()}.zip"
    zip_path = os.path.join(settings.OUTPUT_DIR, zip_name)
    output_format = form_data.get('output_format', 'docx')
    convert_flag = form_data.get('convert_pdf')
    anchor_ipfs = str(form_data.get('anchor_ipfs', 'false')).lower() == 'true'
    classification = form_data.get('classification', 'public')

    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, ctx in enumerate(contexts):
                doc_base = f"{base_name}_{ctx.get('ID', i+1)}"
                try:
                    # Usar el servicio centralizado para generar cada documento del lote
                    content_to_use = tmpl_content if not tmpl_filename.endswith('.md') else template_content_str.encode('utf-8')
                    
                    out_name = await internal_generate_document(
                        template_filename=tmpl_filename,
                        context=ctx,
                        output_format=output_format,
                        convert_pdf=bool(convert_flag),
                        template_content=content_to_use,
                        custom_filename=doc_base,
                        output_dir=temp_dir,
                        anchor_ipfs=anchor_ipfs,
                        classification=classification,
                        user_id=current_user.id
                    )
                    
                    final_path = os.path.join(temp_dir, out_name)
                    if final_path and os.path.exists(final_path):
                        zf.write(final_path, arcname=out_name)

                        # Email
                        if send_email_flag:
                            recipient = ctx.get(recipient_email_col)
                            if recipient:
                                email_ctx = ctx.copy()
                                email_ctx['filename'] = out_name
                                subj = jinja2.Template(subject_tmpl_str).render(email_ctx)
                                bdy = jinja2.Template(body_tmpl_str).render(email_ctx)
                                await send_email_with_gmail(creds, recipient, subj, bdy, final_path)

                except Exception as e:
                    logger.error(f"Error procesando item {i} en lote: {e}")
                    # Continuar con el siguiente item
                    continue

    # Verify zip has content
    failed_batch = False
    with zipfile.ZipFile(zip_path, 'r') as zf_check:
        if len(zf_check.namelist()) == 0:
            failed_batch = True

    if failed_batch:
        raise HTTPException(500, "Falló la generación masiva. Todos los documentos dieron error. Verifique logs del servidor.")

    ipfs_zip_data = None
    if anchor_ipfs:
        try:
            from app.services.ipfs_integration_service import IPFSIntegrationService
            from app.services.crypto_engine import DocClassification
            doc_record = await IPFSIntegrationService.anchor_and_stamp(
                file_path=zip_path,
                classification=DocClassification(classification),
                user_id=current_user.id,
                session=session
            )
            ipfs_zip_data = {
                "cid": doc_record.ipfs_cid,
                "classification": doc_record.classification,
                "gateway_url": doc_record.gateway_url,
                "sha256_original": doc_record.sha256_original
            }
        except Exception as e:
            logger.error(f"Error al anclar el ZIP del lote a IPFS: {e}")

    token = create_file_download_token(zip_name, current_user.id)
    return {
        "success": True,
        "download_url": f"/files/{zip_name}?token={token}",
        "filename": zip_name,
        "ipfs": ipfs_zip_data
    }



from pydantic import BaseModel
from typing import List
import datetime

class MarkdownToDocRequest(BaseModel):
    markdown_content: str
    filename: Optional[str] = None
    format: str = "docx"

@router.post("/api/generation/markdown-to-document")
async def markdown_to_document(
    payload: MarkdownToDocRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Convierte contenido Markdown de un chat directamente a un documento de Word (.docx) o PDF.
    """
    try:
        # Sanitizar el nombre del archivo
        base_name = payload.filename or "Documento_Generado"
        base_name = "".join([c for c in base_name if c.isalnum() or c in (' ', '-', '_')]).strip()
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{base_name.replace(' ', '_')}_{ts}"
        
        # Crear directorio temporal si no existe
        target_dir = settings.OUTPUT_DIR
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        temp_md_name = f"temp_{uuid.uuid4()}.md"
        temp_md_path = os.path.join(target_dir, temp_md_name)
        
        # Guardar el contenido Markdown
        with open(temp_md_path, "w", encoding="utf-8") as f:
            f.write(payload.markdown_content)
            
        # Determinar el formato de salida y realizar la conversión
        out_name = None
        from app.services.document_service import convert_md_to_docx, convert_md_to_pdf
        
        if payload.format.lower() == "pdf":
            out_path = await convert_md_to_pdf(temp_md_path, target_dir)
            if out_path:
                # Renombrar al nombre final deseado
                desired_name = f"{safe_filename}.pdf"
                desired_path = os.path.join(target_dir, desired_name)
                if os.path.exists(out_path):
                    if os.path.exists(desired_path):
                        os.remove(desired_path)
                    os.rename(out_path, desired_path)
                    out_name = desired_name
        else:
            out_path = await convert_md_to_docx(temp_md_path, target_dir)
            if out_path:
                # Renombrar al nombre final deseado
                desired_name = f"{safe_filename}.docx"
                desired_path = os.path.join(target_dir, desired_name)
                if os.path.exists(out_path):
                    if os.path.exists(desired_path):
                        os.remove(desired_path)
                    os.rename(out_path, desired_path)
                    out_name = desired_name
                    
        # Eliminar archivo markdown temporal
        if os.path.exists(temp_md_path):
            os.remove(temp_md_path)
            
        if not out_name:
            raise HTTPException(status_code=500, detail="La conversión de Markdown a documento falló.")
            
        token = create_file_download_token(out_name, current_user.id)
        return {
            "success": True,
            "filename": out_name,
            "download_url": f"/files/{out_name}?token={token}"
        }
    except Exception as e:
        logger.error(f"Error en markdown_to_document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files/{filename}")
async def get_file(
    filename: str,
    token: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Descarga un archivo generado de forma segura.
    
    Permite el acceso si el usuario está autenticado en la plataforma, 
    o si se provee un token criptográfico de descarga válido (para accesos externos seguros).
    """
    # Sanitizar el nombre de archivo para prevenir path traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(settings.OUTPUT_DIR, safe_filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(404, "Archivo no encontrado")
        
    # Validar autorización: usuario autenticado o token firmado válido
    authorized = False
    if current_user is not None:
        authorized = True
    elif token and verify_public_download_token(token, safe_filename):
        authorized = True
        
    if not authorized:
        raise HTTPException(
            status_code=403, 
            detail="No autorizado para descargar este archivo. Se requiere iniciar sesión o un token de acceso válido."
        )
        
    return FileResponse(
        path=file_path,
        media_type='application/octet-stream',
        filename=safe_filename,
        headers={"Content-Disposition": f"attachment; filename=\"{safe_filename}\""}
    )
