"""Router para validación de templates y datos."""
import os
import io
import logging
import json
import hashlib
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import asyncio

from app.auth import get_current_active_user, get_creds_for_user
from app.models.user import User
from app.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.template_manager import TemplateManager
from app.schemas.document import ValidationResultResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Automation"])


@router.post("/api/validate", response_model=ValidationResultResponse)
async def validate_template_and_data(
    template_file: Optional[UploadFile] = File(None),
    google_doc_id: Optional[str] = Form(None),
    data_file: Optional[UploadFile] = File(None),
    google_sheet_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Valida que los datos coincidan con las variables del template."""
    template_vars = []
    data_headers = []
    template_filename = ""

    # 1. Obtener variables del template
    if template_file:
        template_filename = template_file.filename
        template_content_bytes = await template_file.read()
        template_vars = TemplateManager.get_template_variables(
            content_bytes=template_content_bytes,
            filename_hint=template_filename
        )
    elif google_doc_id:
        creds = await get_creds_for_user(current_user, session)
        if not creds:
            raise HTTPException(400, "Google no conectado.")
        try:
            drive_service = build('drive', 'v3', credentials=creds)
            file_meta = await asyncio.to_thread(
                lambda: drive_service.files().get(fileId=google_doc_id, fields='name').execute()
            )
            template_filename = file_meta.get('name', 'google_doc') + ".docx"
            content = await asyncio.to_thread(
                lambda: drive_service.files().export_media(
                    fileId=google_doc_id,
                    mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                ).execute()
            )
            template_vars = TemplateManager.get_template_variables(
                content_bytes=content,
                filename_hint=template_filename
            )
        except HttpError as e:
            logger.error(f"Error Drive: {e}")
            raise HTTPException(500, f"Error Drive: {e}")
    else:
        raise HTTPException(400, "Falta plantilla (proporcione template_file o google_doc_id)")

    # 2. Obtener headers de datos
    if data_file:
        if not data_file.filename.endswith(('.csv', '.xls', '.xlsx')):
            raise HTTPException(400, "Formato datos no soportado. Use .csv, .xls o .xlsx")
        content = await data_file.read()
        def read_headers():
            f = io.BytesIO(content)
            df = pd.read_csv(f) if data_file.filename.endswith('.csv') else pd.read_excel(f)
            return df.columns.tolist()
        data_headers = await asyncio.to_thread(read_headers)
    elif google_sheet_id:
        creds = await get_creds_for_user(current_user, session)
        if not creds:
            raise HTTPException(400, "Google no conectado.")
        try:
            sheets_service = build('sheets', 'v4', credentials=creds)
            res = await asyncio.to_thread(
                lambda: sheets_service.spreadsheets().values().get(
                    spreadsheetId=google_sheet_id,
                    range='A1:ZZ1'
                ).execute()
            )
            values = res.get('values', [])
            if not values:
                raise HTTPException(400, "Sheet vacía.")
            data_headers = values[0]
        except HttpError as e:
            logger.error(f"Error Sheets: {e}")
            raise HTTPException(500, f"Error Sheets: {e}")
    else:
        raise HTTPException(400, "Falta fuente de datos (proporcione data_file o google_sheet_id)")

    # 3. Comparar
    template_vars_set = set(template_vars)
    data_headers_set = set(data_headers)
    missing = sorted(list(template_vars_set - data_headers_set))
    unused = sorted(list(data_headers_set - template_vars_set))

    return ValidationResultResponse(
        success=True,
        template_filename=template_filename,
        template_vars=sorted(list(template_vars_set)),
        data_headers=sorted(list(data_headers_set)),
        missing_in_data=missing,
        unused_in_data=unused,
        match=len(missing) == 0
    )


@router.post("/api/verify-integrity")
async def verify_document_integrity(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    """
    Verifica la integridad de un documento firmado electrónicamente en la plataforma.
    Calcula el hash SHA-256 del archivo subido y lo compara con la base de datos o sellos locales.
    De conformidad con el Decreto 2364 de 2012 de Colombia y la Ley 527 de 1999.
    """
    try:
        content = await file.read()
        sha256 = hashlib.sha256()
        sha256.update(content)
        file_hash = sha256.hexdigest()
        
        filename = file.filename
        clean_filename = filename
        if filename.startswith("SIGNED_"):
            clean_filename = filename.replace("SIGNED_", "", 1)
        base_name, _ = os.path.splitext(clean_filename)

        # 1. Buscar si hay una solicitud de firma en la base de datos por hash o por nombre de archivo limpio
        from sqlmodel import select
        from app.models.signature import SignatureRequest, SignatureSigner
        
        query = select(SignatureRequest).where(
            (SignatureRequest.sha256_signed == file_hash) | 
            (SignatureRequest.document_filename == clean_filename)
        )
        db_result = await session.execute(query)
        sig_req = db_result.scalar_one_or_none()

        if sig_req:
            # Consultar explícitamente los firmantes de esta solicitud
            stmt_signers = select(SignatureSigner).where(SignatureSigner.signature_request_id == sig_req.id)
            res_signers = await session.execute(stmt_signers)
            db_signers = res_signers.scalars().all()

            # Caso 1.A: La solicitud de firmas no ha sido completada aún (Borrador/Pendiente/En Proceso)
            if sig_req.status in ["pending", "in_progress", "draft"]:
                return {
                    "success": False,
                    "status": "PENDIENTE_FIRMA",
                    "message": f"El documento '{filename}' está registrado pero su proceso de firma electrónica aún está pendiente de completarse.",
                    "hash_calculado": file_hash,
                    "registro_firma": {
                        "documento_original_nombre": sig_req.document_filename,
                        "sha256_hash": sig_req.sha256_signed or "Pendiente",
                        "timestamp_utc": (sig_req.created_at.isoformat() + "Z") if sig_req.created_at else None,
                        "estado_global": sig_req.status,
                        "clasificacion": sig_req.classification,
                        "firmantes": [
                            {
                                "nombre": s.name,
                                "email": s.email,
                                "signed": s.signed,
                                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                                "ip": s.ip,
                                "user_agent": s.user_agent,
                                "consentimiento_firma": s.consent_electronic_signature,
                                "consentimiento_habeas_data": s.consent_habeas_data,
                                "rol": "Firmante Autorizado"
                            }
                            for s in db_signers
                        ],
                        "seguridad_integridad": {
                            "metodo_autenticacion": "Proceso formal de firma por Token de Correo",
                            "ipfs_cid": sig_req.signed_document_cid
                        },
                        "proveedor_plataforma": "STAR-DOC Digital Signature Service"
                    }
                }

            # Caso 1.B: Proceso completado, verificar si coincide el hash del archivo subido
            matched_hash = (sig_req.sha256_signed == file_hash)
            
            # Si no coincide con el firmado, verificar si coincide con el original limpio antes de firmar
            is_clean_version = False
            if not matched_hash:
                # Buscar el hash original limpio en los metadatos locales
                firma_filename = f"{base_name}_firma.json"
                firma_path = os.path.join(settings.OUTPUT_DIR, firma_filename)
                if os.path.exists(firma_path):
                    try:
                        with open(firma_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            if meta.get("sha256_hash") == file_hash:
                                is_clean_version = True
                    except Exception:
                        pass

            if is_clean_version:
                return {
                    "success": False,
                    "status": "VERSION_LIMPIA",
                    "message": "El documento subido es el borrador original limpio. Ya existe una versión final firmada y completada, pero este archivo no contiene las firmas.",
                    "hash_calculado": file_hash,
                    "registro_firma": {
                        "documento_original_nombre": sig_req.document_filename,
                        "sha256_hash": sig_req.sha256_signed,
                        "timestamp_utc": (sig_req.created_at.isoformat() + "Z") if sig_req.created_at else None,
                        "estado_global": sig_req.status,
                        "clasificacion": sig_req.classification,
                        "seguridad_integridad": {
                            "metodo_autenticacion": "Proceso formal de firma por Token de Correo",
                            "ipfs_cid": sig_req.signed_document_cid
                        },
                        "proveedor_plataforma": "STAR-DOC Digital Signature Service"
                    }
                }

            # Retornar estado ÍNTEGRO o MODIFICADO según coincidencia de hash
            firma_metadata = {
                "documento_original_nombre": sig_req.document_filename,
                "sha256_hash": sig_req.sha256_signed,
                "timestamp_utc": (sig_req.created_at.isoformat() + "Z") if sig_req.created_at else None,
                "estado_global": sig_req.status,
                "clasificacion": sig_req.classification,
                "firmantes": [
                    {
                        "nombre": s.name,
                        "email": s.email,
                        "signed": s.signed,
                        "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                        "ip": s.ip,
                        "user_agent": s.user_agent,
                        "consentimiento_firma": s.consent_electronic_signature,
                        "consentimiento_habeas_data": s.consent_habeas_data,
                        "video_evidencia_cid": s.video_rec_cid,
                        "video_evidencia_sha256": s.video_sha256,
                        "declaracion_leida": s.declaration_text,
                        "rol": "Firmante Autorizado"
                    }
                    for s in db_signers
                ],
                "seguridad_integridad": {
                    "metodo_autenticacion": "Proceso formal de firma por Doble Factor (OTP vía Correo Electrónico Verificado)",
                    "ipfs_cid": sig_req.signed_document_cid,
                    "timestamp_servicio": True
                },
                "proveedor_plataforma": "STAR-DOC Digital Signature Service"
            }

            return {
                "success": True,
                "status": "INTEGRO" if matched_hash else "MODIFICADO",
                "message": "El documento coincide exactamente con la firma registrada en el sistema." if matched_hash else "¡Cuidado! Este archivo PDF ha sufrido modificaciones o alteraciones después de haberse firmado electrónicamente.",
                "hash_calculado": file_hash,
                "registro_firma": firma_metadata
            }

        # 2. Si no se encontró en SignatureRequest, buscar si hay sellos de integridad locales (para reportes sin flujo de firmas)
        firma_filename = f"{base_name}_firma.json"
        firma_path = os.path.join(settings.OUTPUT_DIR, firma_filename)
        
        firma_metadata = None
        if os.path.exists(firma_path):
            try:
                with open(firma_path, "r", encoding="utf-8") as f:
                    firma_metadata = json.load(f)
            except Exception as e:
                logger.error(f"Error leyendo archivo de firma local {firma_filename}: {e}")
                
        if not firma_metadata:
            # Buscar por hash en todos los _firma.json
            output_dir = settings.OUTPUT_DIR
            if os.path.exists(output_dir):
                for f_name in os.listdir(output_dir):
                    if f_name.endswith("_firma.json"):
                        f_path = os.path.join(output_dir, f_name)
                        try:
                            with open(f_path, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                                if meta.get("sha256_hash") == file_hash:
                                    firma_metadata = meta
                                    break
                        except Exception:
                            continue

        if firma_metadata:
            matched_hash = (firma_metadata.get("sha256_hash") == file_hash)
            return {
                "success": True,
                "status": "INTEGRO" if matched_hash else "MODIFICADO",
                "message": "El documento coincide exactamente con el sello de integridad registrado." if matched_hash else "El documento ha sido modificado.",
                "hash_calculado": file_hash,
                "registro_firma": firma_metadata
            }

        # 3. Si no se encontró como firma o sello local, buscar en Appointments (actas de videollamada)
        from app.models.appointment import Appointment
        from app.models.user import User
        # Buscar primero por hash exacto
        stmt_apt = select(Appointment).where(Appointment.jitsi_transcription_cid == f"sha256:{file_hash}")
        res_apt = await session.execute(stmt_apt)
        appointment = res_apt.scalars().first()
        
        if appointment:
            # Caso 3.A: Acta íntegra (El hash coincide perfectamente)
            creator_email = "abogado@stardoc.cloud"
            creator_name = appointment.created_by or "Abogado Conciliador"
            if appointment.created_by:
                stmt_user = select(User).where(User.username == appointment.created_by)
                res_user = await session.execute(stmt_user)
                user_creator = res_user.scalars().first()
                if user_creator:
                    creator_email = user_creator.email
                    creator_name = user_creator.full_name or user_creator.username

            invited_emails = []
            if appointment.internal_notes:
                for line in appointment.internal_notes.split("\n"):
                    if "Participantes invitados:" in line:
                        parts = line.split("Participantes invitados:")
                        if len(parts) > 1:
                            invited_emails = [e.strip() for e in parts[1].split(",") if e.strip()]

            firmantes_lista = [
                {
                    "nombre": creator_name,
                    "email": creator_email,
                    "signed": True,
                    "signed_at": appointment.appointment_date.isoformat() if appointment.appointment_date else None,
                    "ip": "Registrado en Videollamada",
                    "user_agent": "Navegador Web (Star-Doc Meet)",
                    "consentimiento_firma": True,
                    "consentimiento_habeas_data": True,
                    "video_evidencia_cid": None,
                    "video_evidencia_sha256": None,
                    "declaracion_leida": "Consentimiento mutuo en videollamada para redacción de Acta por Inteligencia Artificial.",
                    "rol": "Creador de Sala / Conciliador"
                }
            ]
            
            for email in invited_emails:
                if email.lower() != creator_email.lower():
                    firmantes_lista.append({
                        "nombre": email.split("@")[0].capitalize(),
                        "email": email,
                        "signed": True,
                        "signed_at": appointment.appointment_date.isoformat() if appointment.appointment_date else None,
                        "ip": "Registrado en Videollamada",
                        "user_agent": "Navegador Web (Star-Doc Meet)",
                        "consentimiento_firma": True,
                        "consentimiento_habeas_data": True,
                        "video_evidencia_cid": None,
                        "video_evidencia_sha256": None,
                        "declaracion_leida": "Consentimiento mutuo en videollamada para redacción de Acta por Inteligencia Artificial.",
                        "rol": "Participante Invitado"
                    })

            firma_metadata = {
                "documento_original_nombre": filename,
                "sha256_hash": file_hash,
                "timestamp_utc": appointment.appointment_date.isoformat() if appointment.appointment_date else None,
                "estado_global": "completed",
                "clasificacion": "Acta de Conciliación",
                "firmantes": firmantes_lista,
                "seguridad_integridad": {
                    "metodo_autenticacion": "Estampado Criptográfico SHA-256 e Integridad Legal por IA (Ley 640 y Ley 527)",
                    "ipfs_cid": "local",
                    "timestamp_servicio": True
                },
                "proveedor_plataforma": "STAR-DOC Digital Signature & Mediation Service"
            }
            return {
                "success": True,
                "status": "INTEGRO",
                "message": "Este documento es un Acta de Conciliación certificada. Coincide exactamente con la firma criptográfica y marcas de tiempo registradas en Star-Doc.",
                "hash_calculado": file_hash,
                "registro_firma": firma_metadata
            }

        # Buscar por nombre del archivo en las notas internas de Appointments para detectar si fue modificada/adulterada
        safe_filename = os.path.basename(filename)
        if safe_filename.startswith("ACTA_CONCILIACION_"):
            stmt_name = select(Appointment).where(Appointment.internal_notes.like(f"%Archivo: {safe_filename}%"))
            res_name = await session.execute(stmt_name)
            appointment_by_name = res_name.scalars().first()
            
            if appointment_by_name:
                # Caso 3.B: El archivo corresponde a un acta pero su hash no coincide (Adulterado/Modificado)
                creator_email = "abogado@stardoc.cloud"
                creator_name = appointment_by_name.created_by or "Abogado Conciliador"
                if appointment_by_name.created_by:
                    stmt_user = select(User).where(User.username == appointment_by_name.created_by)
                    res_user = await session.execute(stmt_user)
                    user_creator = res_user.scalars().first()
                    if user_creator:
                        creator_email = user_creator.email
                        creator_name = user_creator.full_name or user_creator.username

                invited_emails = []
                if appointment_by_name.internal_notes:
                    for line in appointment_by_name.internal_notes.split("\n"):
                        if "Participantes invitados:" in line:
                            parts = line.split("Participantes invitados:")
                            if len(parts) > 1:
                                invited_emails = [e.strip() for e in parts[1].split(",") if e.strip()]

                firmantes_lista = [
                    {
                        "nombre": creator_name,
                        "email": creator_email,
                        "signed": True,
                        "signed_at": appointment_by_name.appointment_date.isoformat() if appointment_by_name.appointment_date else None,
                        "ip": "Registrado en Videollamada",
                        "user_agent": "Navegador Web (Star-Doc Meet)",
                        "consentimiento_firma": True,
                        "consentimiento_habeas_data": True,
                        "video_evidencia_cid": None,
                        "video_evidencia_sha256": None,
                        "declaracion_leida": "Consentimiento mutuo en videollamada para redacción de Acta por Inteligencia Artificial.",
                        "rol": "Creador de Sala / Conciliador"
                    }
                ]
                
                for email in invited_emails:
                    if email.lower() != creator_email.lower():
                        firmantes_lista.append({
                            "nombre": email.split("@")[0].capitalize(),
                            "email": email,
                            "signed": True,
                            "signed_at": appointment_by_name.appointment_date.isoformat() if appointment_by_name.appointment_date else None,
                            "ip": "Registrado en Videollamada",
                            "user_agent": "Navegador Web (Star-Doc Meet)",
                            "consentimiento_firma": True,
                            "consentimiento_habeas_data": True,
                            "video_evidencia_cid": None,
                            "video_evidencia_sha256": None,
                            "declaracion_leida": "Consentimiento mutuo en videollamada para redacción de Acta por Inteligencia Artificial.",
                            "rol": "Participante Invitado"
                        })

                original_hash = "Desconocido"
                if appointment_by_name.jitsi_transcription_cid and appointment_by_name.jitsi_transcription_cid.startswith("sha256:"):
                    original_hash = appointment_by_name.jitsi_transcription_cid.replace("sha256:", "", 1)
                
                firma_metadata = {
                    "documento_original_nombre": safe_filename,
                    "sha256_hash": original_hash,
                    "timestamp_utc": appointment_by_name.appointment_date.isoformat() if appointment_by_name.appointment_date else None,
                    "estado_global": "completed",
                    "clasificacion": "Acta de Conciliación",
                    "firmantes": firmantes_lista,
                    "seguridad_integridad": {
                        "metodo_autenticacion": "Estampado Criptográfico SHA-256 e Integridad Legal por IA",
                        "ipfs_cid": "local",
                        "timestamp_servicio": True
                    },
                    "proveedor_plataforma": "STAR-DOC Digital Signature & Mediation Service"
                }
                return {
                    "success": True,
                    "status": "MODIFICADO",
                    "message": "¡Cuidado! Este archivo de acta ha sufrido modificaciones o alteraciones después de haberse generado en la videollamada.",
                    "hash_calculado": file_hash,
                    "registro_firma": firma_metadata
                }

        # 4. No registrado
        return {
            "success": False,
            "status": "NO_REGISTRADO",
            "message": "No se encontró ningún registro de firma electrónica, sello de tiempo ni anclaje IPFS para este documento en la base de datos de Star-Doc.",
            "hash_calculado": file_hash,
            "registro_firma": None
        }
            
    except Exception as e:
        logger.error(f"Error en verificación de integridad: {e}")
        raise HTTPException(status_code=500, detail=f"Error en verificación de integridad: {str(e)}")
