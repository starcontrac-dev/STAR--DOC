"""
Router de API para la gestión de salas de videoconferencia de Jitsi Meet y evidencias de Video-Firma.
"""
import os
import uuid
import logging
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel

from app.database import get_session
from app.auth import get_current_user_optional, get_current_active_user
from app.models.user import User
from app.models.appointment import Appointment
from app.models.signature import SignatureRequest
from app.services.jitsi_service import JitsiService
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.crypto_engine import DocClassification
from app.core.config import settings
from app.core.utils import get_base_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings", tags=["Meetings / Videoconferencing"])

@router.get("/declaration-text")
async def get_declaration_text(signer_name: str = "Invitado", document_name: str = "Contrato"):
    """
    Retorna la declaración preestablecida legal en viva voz para lectura del firmante.
    """
    text = (
        f"Yo, {signer_name}, acepto voluntariamente los términos y condiciones. "
        f"Firmo de forma electrónica y consciente de sus efectos legales."
    )
    return {"text": text}

@router.post("/generate-url")
async def generate_meeting_url(
    appointment_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_session)
):
    """
    Genera y registra el enlace de reunión Jitsi Meet para una cita de asesoría.
    """
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="La cita especificada no existe.")
    
    # Generar sala si no existe
    if not appointment.jitsi_room_name:
        appointment.jitsi_room_name = f"stardoc_room_{uuid.uuid4().hex[:12]}"
    
    user_name = current_user.username if current_user else appointment.lead_name or "Invitado"
    user_email = current_user.email if current_user else appointment.lead_email or "invitado@stardoc.cloud"
    is_moderator = True if current_user and current_user.role in ("admin", "abogado") else False
    
    # Generar URL con el servicio
    meeting_info = JitsiService.generate_meeting_url(
        room_name=appointment.jitsi_room_name,
        user_name=user_name,
        user_email=user_email,
        is_moderator=is_moderator
    )
    
    # Actualizar base de datos
    appointment.meeting_link = meeting_info["url"]
    # Configurar el texto de la declaración legal por defecto para esta cita
    if not appointment.declaration_text:
        appointment.declaration_text = (
            f"Yo declaro voluntariamente que apruebo todos los acuerdos de esta sesión de conciliación "
            f"agendada para el día {appointment.appointment_date}."
        )
    
    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)
    
    return {
        "success": True,
        "meeting_url": meeting_info["url"],
        "room_name": appointment.jitsi_room_name,
        "domain": meeting_info["domain"],
        "is_moderator": is_moderator
    }

@router.post("/upload-evidence/{signer_token}")
async def upload_signature_video_evidence(
    signer_token: str,
    request: Request,
    db: AsyncSession = Depends(get_session)
):
    """
    Recibe la grabación de video de consentimiento local, soportando tanto formato JSON (Base64)
    como Multipart/Form-Data para compatibilidad de caché y prevención de UnicodeDecodeErrors.
    """
    logger.info(f"Recibiendo video evidencia de firma para el token: {signer_token}")
    
    from app.models.signature import SignatureSigner
    
    # 1. Buscar la solicitud de firma y el firmante por token
    stmt = select(SignatureSigner).where(SignatureSigner.token == signer_token)
    res = await db.execute(stmt)
    target_signer = res.scalar_one_or_none()
            
    if not target_signer:
        raise HTTPException(status_code=404, detail="Token de firma no válido o expirado.")
        
    found_req = target_signer.request
    
    # Validar expiración
    if found_req.expiration < datetime.utcnow() and found_req.status != "expired":
        found_req.status = "expired"
        db.add(found_req)
        await db.commit()
        raise HTTPException(status_code=400, detail="La solicitud de firma ha expirado.")
        
    if target_signer.signed:
        raise HTTPException(status_code=400, detail="Este firmante ya ha completado su proceso.")
        
    content_type = request.headers.get("content-type", "")
    temp_path = None
    video_bytes = None
    declaration_read = ""
    ext = ".webm"
    
    try:
        import base64
        
        if "application/json" in content_type:
            payload = await request.json()
            video_base64 = payload.get("video_base64", "")
            declaration_read = payload.get("declaration_read", "")
            
            header, base64_data = "", video_base64
            if "," in video_base64:
                header, base64_data = video_base64.split(",", 1)
                
            # Limpiar espacios en blanco, saltos de línea, caracteres URL-safe y caracteres no válidos
            import re
            
            # Reemplazar caracteres URL-safe
            base64_data = base64_data.replace('-', '+').replace('_', '/')
            
            # Filtrar solo caracteres válidos del alfabeto Base64 (sin incluir '=')
            base64_clean = re.sub(r'[^A-Za-z0-9+/]', '', base64_data)
            
            # Corregir relleno (padding) de la cadena Base64
            # Si el residuo es 1, descartamos el último carácter huérfano para evitar binascii.Error (Python 3.13)
            missing_padding = len(base64_clean) % 4
            if missing_padding == 1:
                base64_clean = base64_clean[:-1]
                missing_padding = 0
                
            if missing_padding == 2:
                base64_clean += '=='
            elif missing_padding == 3:
                base64_clean += '='
                
            video_bytes = base64.b64decode(base64_clean)
            
            if "mp4" in header.lower() or "mp4" in video_base64[:30].lower():
                ext = ".mp4"
        else:
            # Fallback Multipart/Form-Data para compatibilidad con código en caché
            form = await request.form()
            file = form.get("file")
            declaration_read = form.get("declaration_read", "")
            
            if not file:
                raise HTTPException(status_code=400, detail="No se encontró el archivo de video en la petición multipart.")
                
            video_bytes = await file.read()
            content_type_file = file.content_type or ""
            if "webm" in content_type_file:
                ext = ".webm"
            elif "mp4" in content_type_file:
                ext = ".mp4"

        unique_filename = f"EVIDENCE_SIGN_{signer_token}_{uuid.uuid4().hex[:8]}{ext}"
        temp_path = os.path.join(settings.OUTPUT_DIR, unique_filename)
        
        with open(temp_path, "wb") as buffer:
            buffer.write(video_bytes)
            
        # 3. Anclar el video a IPFS Kubo.
        video_class_str = "public"
        if found_req.classification:
            video_class_str = str(found_req.classification).strip().lower()
            
        if video_class_str != "public":
            logger.info(f"🔒 Encriptando video evidencia de firma con clasificación: {video_class_str}")
            try:
                video_classification = DocClassification(video_class_str)
            except Exception:
                video_classification = DocClassification.CHAIN_OF_CUSTODY
        else:
            video_classification = DocClassification.PUBLIC
 
        doc_ipfs_record = await IPFSIntegrationService.anchor_and_stamp(
            file_path=temp_path,
            classification=video_classification,
            user_id=found_req.user_id,
            session=db
        )
        
        # 4. Actualizar el firmante en la base de datos
        target_signer.video_rec_cid = doc_ipfs_record.ipfs_cid
        target_signer.video_sha256 = doc_ipfs_record.sha256_original
        target_signer.declaration_text = declaration_read
        logger.info(f"Video asociado al firmante. IPFS CID: {doc_ipfs_record.ipfs_cid}")
        
        db.add(target_signer)
        await db.commit()
        await db.refresh(target_signer)
        
        return {
            "success": True,
            "message": "Evidencia de video grabada y anclada a IPFS con éxito.",
            "ipfs_cid": doc_ipfs_record.ipfs_cid,
            "sha256": doc_ipfs_record.sha256_original
        }
        
    except Exception as e:
        logger.error(f"Error procesando video de evidencia de firma: {e}", exc_info=True)
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error interno al procesar el video: {str(e)}")

class MinutesRequest(BaseModel):
    transcription: Optional[str] = None

@router.post("/generate-minutes/{room_name}")
async def generate_meeting_minutes(
    room_name: str,
    payload_data: MinutesRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Toma la transcripción del audio de la reunión y genera automáticamente un Acta de Conciliación
    formateada con IA (Gemini 2.5 Pro), guardándola en output y anclándola a IPFS.
    """
    logger.info(f"Generando acta de reunión para la sala: {room_name}")
    
    # 1. Obtener la cita asociada a la sala
    stmt = select(Appointment).where(Appointment.jitsi_room_name == room_name)
    res = await db.execute(stmt)
    appointment = res.scalars().first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="No se encontró ninguna cita asociada a esta sala de Jitsi.")
        
    # 2. Recuperar la transcripción desde Redis o el payload
    transcription_text = payload_data.transcription
    if not transcription_text or transcription_text.strip() == "":
        try:
            from app.core.redis_client import get_redis
            redis = await get_redis(db=3)
            key = f"meeting_transcription:{room_name}"
            cached_transcription = await redis.get(key)
            if cached_transcription:
                transcription_text = cached_transcription.decode("utf-8") if isinstance(cached_transcription, bytes) else cached_transcription
                logger.info(f"Transcripción recuperada exitosamente desde Redis para la sala: {room_name} ({len(transcription_text)} caracteres)")
        except Exception as redis_err:
            logger.warning(f"No se pudo recuperar la transcripción desde Redis: {redis_err}")

    if not transcription_text or transcription_text.strip() == "":
        raise HTTPException(
            status_code=400, 
            detail="No se encontró ninguna transcripción disponible (Redis vacío y payload vacío)."
        )

    try:
        # 3. Invocar el AIService singleton para estructurar el acta con Gemini 2.5 Pro (temperatura baja)
        from app.services.ai_service import AIService
        ai = AIService()
        
        system_prompt = (
            "Eres un abogado experto en Derecho Civil, Comercial y de Conciliaciones en la República de Colombia "
            "con más de 30 años de experiencia jurídica. Redacta de forma extremadamente formal, clara y estructurada "
            "un Acta de Acuerdo de Conciliación en formato Markdown (MD) basada únicamente en los puntos discutidos "
            "y la transcripción provista de la videollamada. Utiliza las bases de la Ley 640 de 2001 y la Ley 2213 de 2022. "
            "El acta debe contener: fecha de la sesión, identificación de las partes, objeto de conciliación, obligaciones "
            "de dar/hacer claras y plazos de cumplimiento."
        )
        
        prompt = (
            f"Cita asociada: Asesoría/Conciliación de {appointment.lead_name} ({appointment.lead_email}).\n"
            f"Motivo inicial agendado: {appointment.reason}\n\n"
            f"Transcripción textual de la reunión en caliente:\n\"\"\"\n{transcription_text}\n\"\"\"\n\n"
            f"Genera el documento legal final en formato Markdown:"
        )
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2, # Exactitud sobre creatividad
                "maxOutputTokens": 4000
            },
            "systemInstruction": {"parts": [{"text": system_prompt}]}
        }
        
        ai_response = await ai.generate_content(payload)
        acta_markdown = ai_response.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text")
        
        if not acta_markdown:
            raise ValueError("No se pudo obtener texto redactado por Gemini.")
            
        # 3. Guardar el archivo Markdown físico en output
        filename = f"ACTA_CONCILIACION_{room_name}_{uuid.uuid4().hex[:6]}.md"
        filepath = os.path.join(settings.OUTPUT_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(acta_markdown)
            
        # 4. Anclar el Acta generada a IPFS Kubo de forma confidencial (CHAIN_OF_CUSTODY)
        doc_ipfs_record = await IPFSIntegrationService.anchor_and_stamp(
            file_path=filepath,
            classification=DocClassification.CHAIN_OF_CUSTODY,
            user_id=current_user.id,
            session=db
        )
        
        # 5. Asociar la transcripción y el acta a la cita
        appointment.jitsi_transcription_cid = doc_ipfs_record.ipfs_cid
        appointment.internal_notes = (
            f"Acta de Conciliación autogenerada y anclada a IPFS con CID: {doc_ipfs_record.ipfs_cid}\n"
            f"Resumen de acta: {acta_markdown[:150]}..."
        )
        
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        
        return {
            "success": True,
            "filename": filename,
            "ipfs_cid": doc_ipfs_record.ipfs_cid,
            "sha256": doc_ipfs_record.sha256_original,
            "acta_preview": acta_markdown[:400] + "..."
        }
        
    except Exception as e:
        logger.error(f"Error autogenerando acta de conciliación con Gemini: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al procesar el acta legal con IA: {str(e)}")


@router.post("/process-audio/{room_name}")
async def process_meeting_audio(
    room_name: str,
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Recibe la grabación de audio de la videollamada, la sube temporalmente a la Gemini File API,
    obtiene la transcripción/diarización y estructura el Acta de Conciliación en formato Markdown
    con base en la legislación colombiana (Ley 640 de 2001), guardándola de forma local en base de datos.
    Tanto el archivo de audio local como el de Gemini se eliminan de inmediato tras completarse.
    """
    logger.info(f"Recibiendo grabación de audio para procesar en la sala: {room_name}")
    
    # 1. Obtener la cita asociada a la sala
    stmt = select(Appointment).where(Appointment.jitsi_room_name == room_name)
    res = await db.execute(stmt)
    appointment = res.scalars().first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="No se encontró ninguna cita asociada a esta sala de Jitsi.")
        
    # 2. Guardar el archivo de audio localmente en output de forma temporal
    audio_ext = ".webm"
    if audio_file.filename:
        _, ext = os.path.splitext(audio_file.filename)
        if ext:
            audio_ext = ext
            
    unique_audio_filename = f"AUDIO_MEETING_{room_name}_{uuid.uuid4().hex[:8]}{audio_ext}"
    audio_path = os.path.join(settings.OUTPUT_DIR, unique_audio_filename)
    
    try:
        with open(audio_path, "wb") as buffer:
            content = await audio_file.read()
            buffer.write(content)
    except Exception as io_err:
        logger.error(f"Error al escribir archivo de audio temporal localmente: {io_err}")
        raise HTTPException(status_code=500, detail="Error al guardar el archivo de audio temporal en el servidor.")
        
    uploaded_file_uris = []
    gemini_file_info = None
    ai_response = None
    last_exception = None
    
    # 4. Prompt y estructuración de acta minimalista y estrictamente fiel al audio (de constancia de acuerdos)
    system_prompt = (
        "Eres un transcriptor y abogado asistente experto en la República de Colombia. "
        "Redacta un Acta de Constancia y Acuerdos de Reunión de manera minimalista y muy concisa, "
        "actuando estrictamente como un transcriptor veraz y resumidor de los hechos. "
        "REGLA CRÍTICA: No asumas, inventes, ni agregues cláusulas, obligaciones, plazos, nombres o información "
        "que no esté explícitamente dicha en el audio de la reunión. Si una parte no se acordó o no se discutió, "
        "no la inventes bajo ninguna circunstancia. Tampoco inventes que es un acta de conciliación, debe ser presentada "
        "únicamente como un acta de constancia de lo discutido y acordado en la reunión. El acta debe contener únicamente "
        "un resumen fiel, ordenado y directo de lo que se dijo en el meet, estructurado formalmente en formato Markdown (MD)."
    )
    
    prompt = (
        f"Cita asociada: Reunión de {appointment.lead_name} ({appointment.lead_email}).\n"
        f"Motivo inicial agendado: {appointment.reason}\n\n"
        "Analiza detalladamente el audio. Identifica y transcribe los diálogos diarizando de forma concisa "
        "a los hablantes (Participantes). "
        "A partir de lo realmente dicho en la reunión, redacta un Acta de Constancia de Reunión resumida "
        "y minimalista en formato Markdown (MD) libre de alucinaciones, datos imaginados o agregados no discutidos:"
    )

    try:
        from app.services.ai_service import AIService
        ai = AIService()
        
        max_attempts = 3
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                # Subir el audio a la Gemini File API (rotación automática)
                gemini_file_info = await ai.upload_file_to_gemini(audio_path, audio_file.content_type or "audio/webm")
                uploaded_file_uris.append((gemini_file_info["file_uri"], gemini_file_info["file_name"], gemini_file_info["api_key"]))
                
                payload = {
                    "contents": [{
                        "parts": [
                            {
                                "fileData": {
                                    "mimeType": audio_file.content_type or "audio/webm",
                                    "fileUri": gemini_file_info["file_uri"]
                                }
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.1,  # Temperatura baja para evitar creatividad y alucinaciones
                        "maxOutputTokens": 3000  # Limitar tokens de salida para mejorar sustancialmente la latencia
                    },
                    "systemInstruction": {"parts": [{"text": system_prompt}]}
                }
                
                logger.info(f"Enviando audio a Gemini para transcripción diarizada y redacción de acta minimalista (Intento {attempt}/{max_attempts})...")
                ai_response = await ai.generate_content(payload, api_key=gemini_file_info["api_key"])
                # Si llega aquí, la consulta fue exitosa
                break
            except Exception as ex_attempt:
                logger.warning(f"⚠️ Fallo en el intento {attempt} de redacción de acta: {ex_attempt}")
                last_exception = ex_attempt
                # Marcar la clave fallida en cooldown temporalmente en memoria
                if gemini_file_info and "api_key" in gemini_file_info:
                    try:
                        # Extraer índice de la clave que falló
                        idx = ai.api_keys.index(gemini_file_info["api_key"])
                        ai.invalid_keys.add(idx)  # Sacarla del pool para este flujo
                    except ValueError:
                        pass
                await asyncio.sleep(1.0)
                
        if not ai_response:
            raise last_exception or Exception("Fallo total al interactuar con Gemini en todos los reintentos.")

        acta_markdown = ai_response.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text")
        
        if not acta_markdown:
            raise ValueError("No se pudo obtener texto redactado por Gemini.")
            
        # 5. Guardar el archivo de acta Markdown físico localmente en output
        filename = f"ACTA_CONSTANCIA_{room_name}_{uuid.uuid4().hex[:6]}.md"
        filepath = os.path.join(settings.OUTPUT_DIR, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(acta_markdown)
            
        # Calcular el hash SHA256 local
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f_hash:
            for byte_block in iter(lambda: f_hash.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256_val = sha256_hash.hexdigest()
        
        # 6. Registrar en base de datos la constancia criptográfica del acta generada
        appointment.jitsi_transcription_cid = f"sha256:{sha256_val}"
        appointment.internal_notes = (
            f"Acta de Constancia y Acuerdos autogenerada por IA (Local) asociada a la videollamada. Archivo: {filename}\n"
            f"Hash SHA256: {sha256_val}\n"
            f"Resumen del acta:\n{acta_markdown[:600]}..."
        )
        db.add(appointment)
        await db.commit()
        await db.refresh(appointment)
        
        # Enviar el acta por correo a los participantes
        try:
            from app.services.email import EmailService
            from app.models.user import User
            
            # Obtener el creador
            creator_email = "abogado@stardoc.cloud"
            creator_name = appointment.created_by or "Abogado Conciliador"
            if appointment.created_by:
                stmt_user = select(User).where(User.username == appointment.created_by)
                res_user = await db.execute(stmt_user)
                user_creator = res_user.scalars().first()
                if user_creator:
                    creator_email = user_creator.email
                    creator_name = user_creator.full_name or user_creator.username

            # Obtener los invitados
            invited_emails = []
            if appointment.internal_notes:
                for line in appointment.internal_notes.split("\n"):
                    if "Participantes invitados:" in line:
                        parts = line.split("Participantes invitados:")
                        if len(parts) > 1:
                            invited_emails = [e.strip() for e in parts[1].split(",") if e.strip()]

            # Unificar destinatarios únicos
            recipients = {creator_email.lower(): (creator_email, creator_name)}
            for email in invited_emails:
                cleaned_email = email.lower().strip()
                if cleaned_email and cleaned_email not in recipients:
                    recipients[cleaned_email] = (email, email.split("@")[0].capitalize())

            # URL de descarga en la página de verificación pública
            download_url = f"{settings.BASE_URL}/api/meetings/verify-minutes/{filename}"

            for email_addr, (email, name) in recipients.items():
                logger.info(f"Enviando correo con Acta de Constancia de Reunión a {email_addr}")
                await EmailService.send_meeting_minutes_email(
                    recipient_email=email,
                    recipient_name=name,
                    room_name=room_name,
                    minutes_content=acta_markdown,
                    download_url=download_url,
                    sha256_val=sha256_val
                )
        except Exception as mail_err:
            logger.error(f"Error enviando notificaciones del acta por correo: {mail_err}")
        
        return {
            "success": True,
            "filename": filename,
            "ipfs_cid": "local",
            "sha256": sha256_val,
            "acta_preview": acta_markdown[:400] + "..."
        }
        
    except Exception as e:
        logger.error(f"Error procesando audio y redactando acta con IA: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al estructurar el acta legal: {str(e)}")
        
    finally:
        # 7. Limpieza estricta y obligatoria de evidencias temporales
        if os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Limpieza: Audio temporal local eliminado con éxito: {audio_path}")
            except Exception as rm_err:
                logger.error(f"No se pudo eliminar el audio local: {rm_err}")
                
        for file_uri, file_name, api_key in uploaded_file_uris:
            try:
                await ai.delete_file_from_gemini(file_name, api_key)
                logger.info(f"Limpieza: Audio temporal {file_name} en Gemini File API eliminado con éxito.")
            except Exception as gemini_rm_err:
                logger.error(f"No se pudo eliminar el audio en Gemini File API para {file_name}: {gemini_rm_err}")


@router.get("/verify-minutes/{filename}")
async def verify_meeting_minutes(
    filename: str,
    db: AsyncSession = Depends(get_session)
):
    """
    Endpoint de auditoría criptográfica. Toma un nombre de archivo de acta, calcula
    su hash SHA-256 en caliente en el disco del servidor, y cruza dicho hash contra
    los registros inmutables de la base de datos para certificar su validez y existencia.
    """
    # 1. Sanitizar el nombre del archivo para prevenir path traversal
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(settings.OUTPUT_DIR, safe_filename)
    
    if not os.path.exists(filepath):
        return {
            "success": False,
            "valid": False,
            "reason": "El archivo de acta solicitado no existe físicamente en el servidor de Star-Doc."
        }
        
    try:
        # 2. Calcular el hash SHA-256 actual del archivo en disco
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        sha256_actual = sha256_hash.hexdigest()
        
        # 3. Buscar en la base de datos la cita asociada a este hash
        target_token = f"sha256:{sha256_actual}"
        stmt = select(Appointment).where(Appointment.jitsi_transcription_cid == target_token)
        res = await db.execute(stmt)
        appointment = res.scalars().first()
        
        if not appointment:
            return {
                "success": True,
                "valid": False,
                "reason": "Alerta: El contenido del archivo de acta ha sido alterado o el hash no se encuentra registrado en el sistema.",
                "sha256_calculated": sha256_actual
            }
            
        # 4. Retornar el reporte de verificación minimalista y profesional
        return {
            "success": True,
            "valid": True,
            "message": "Constancia de Integridad y Existencia Legal verificada exitosamente.",
            "document_details": {
                "filename": safe_filename,
                "sha256_hash": sha256_actual,
                "created_at": appointment.appointment_date.strftime("%Y-%m-%d") if appointment.appointment_date else "Desconocido",
                "room_name": appointment.jitsi_room_name,
                "lead_name": appointment.lead_name,
                "lead_email": appointment.lead_email,
                "reason": appointment.reason
            }
        }
    except Exception as e:
        logger.error(f"Error realizando auditoría del acta {filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Fallo en el proceso de verificación criptográfica: {str(e)}"
        )


from pydantic import EmailStr
from typing import List

class InstantMeetingRequest(BaseModel):
    emails: List[str]
    document_name: Optional[str] = None
    reason: Optional[str] = "Debate y Firma de Documento"
    send_invitations: bool = False
    classification: Optional[str] = "chain_of_custody"
    disable_ipfs: bool = False


@router.post("/create-instant")
async def create_instant_meeting(
    payload: InstantMeetingRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Crea una reunión instantánea (videollamada) de Jitsi Meet, vinculada opcionalmente a un documento,
    y opcionalmente envía invitaciones por correo electrónico a los participantes indicados.
    """
    import uuid
    from datetime import datetime, timedelta
    import pytz
    from app.models.appointment import AppointmentStatus, AppointmentType
    
    room_name = f"stardoc_instant_{uuid.uuid4().hex[:12]}"
    
    # Obtener fecha/hora en la zona horaria de Colombia
    try:
        col_tz = pytz.timezone("America/Bogota")
        now_local = datetime.now(col_tz)
    except Exception:
        now_local = datetime.utcnow()
        
    # Crear la cita en base de datos para registrar la videollamada
    lead_email = payload.emails[0] if payload.emails else "invitado@stardoc.cloud"
    lead_name = f"Reunión de {current_user.username}"
    
    notes = (
        f"Videollamada instantánea. Documento: {payload.document_name or 'Ninguno'}.\n"
        f"Participantes invitados: {', '.join(payload.emails)}"
    )
    if payload.disable_ipfs:
        notes += "\n[IPFS_DISABLED]"

    appointment = Appointment(
        lead_email=lead_email,
        lead_name=lead_name,
        appointment_date=now_local.date(),
        appointment_time=now_local.time(),
        duration_minutes=60,
        appointment_type=AppointmentType.VIDEO_CALL.value,
        reason=payload.reason,
        status=AppointmentStatus.CONFIRMED.value,
        jitsi_room_name=room_name,
        created_by=current_user.username,
        internal_notes=notes
    )
    
    # Generar el enlace de la reunión con JitsiService
    meeting_info = JitsiService.generate_meeting_url(
        room_name=room_name,
        user_name=current_user.username,
        user_email=current_user.email,
        is_moderator=True
    )
    appointment.meeting_link = meeting_info["url"]
    appointment.declaration_text = (
        f"Yo, en calidad de firmante/participante, declaro voluntariamente que apruebo todos los acuerdos "
        f"discutidos sobre el documento {payload.document_name or 'legal'} en esta sesión del día {appointment.appointment_date}."
    )
    
    appointment.generate_token()
    db.add(appointment)
    
    # Crear también la solicitud de firma formal en base de datos para controlar el flujo de firmado y evitar subidas repetidas a IPFS
    if payload.document_name:
        from app.models.signature import SignatureRequest
        
        # Sanitizar nombre
        clean_doc_name = os.path.basename(payload.document_name)
        if clean_doc_name.startswith("SIGNED_"):
            clean_doc_name = clean_doc_name.replace("SIGNED_", "", 1)
            
        # Comprobar si ya existe una solicitud de firma activa para este mismo documento
        stmt_sig = select(SignatureRequest).where(
            SignatureRequest.document_filename == clean_doc_name,
            SignatureRequest.status != "completed",
            SignatureRequest.status != "expired"
        )
        res_sig = await db.execute(stmt_sig)
        sig_req_exists = res_sig.scalars().first()
        
        classification_value = f"{payload.classification}_local" if payload.disable_ipfs else payload.classification
        
        if sig_req_exists:
            # Sincronizar la clasificación elegida para la videollamada con la de la solicitud activa
            if payload.classification:
                sig_req_exists.classification = classification_value
                db.add(sig_req_exists)
        else:
            # Los firmantes requeridos serán: el creador de la videollamada y todos los correos invitados
            from app.models.signature import SignatureSigner
            
            signers_instances = [
                SignatureSigner(
                    name=current_user.username,
                    email=current_user.email,
                    signed=False,
                    signed_at=None,
                    ip=None,
                    user_agent=None,
                    token=str(uuid.uuid4())
                )
            ]
            for email in payload.emails:
                cleaned_email = email.strip().lower()
                if cleaned_email and cleaned_email != current_user.email.lower():
                    signers_instances.append(
                        SignatureSigner(
                            name=cleaned_email.split("@")[0],
                            email=cleaned_email,
                            signed=False,
                            signed_at=None,
                            ip=None,
                            user_agent=None,
                            token=str(uuid.uuid4())
                        )
                    )
            
            sig_req = SignatureRequest(
                user_id=current_user.id,
                document_filename=clean_doc_name,
                status="pending",
                signers=signers_instances,
                expiration=datetime.utcnow() + timedelta(days=7),
                classification=classification_value or "chain_of_custody"
            )
            db.add(sig_req)
        
    await db.commit()
    await db.refresh(appointment)
    
    base_url = get_base_url(request)
    
    # Enviar invitaciones por correo electrónico si se solicita
    invitation_success = []
    if payload.send_invitations and payload.emails:
        from app.services.email import send_email_async
        
        subject = f"Invitación a Videollamada Star-Doc: {payload.reason}"
        doc_query = f"?doc={payload.document_name}" if payload.document_name else ""
        token_connector = "&" if doc_query else "?"
        local_link = f"{base_url}/dashboard/reunion/{room_name}{doc_query}{token_connector}token={appointment.confirmation_token}"
        
        body = (
            f"<div style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;'>"
            f"<h2 style='color: #4f46e5; margin-bottom: 20px;'>Invitación a Videollamada Legal</h2>"
            f"<p>El abogado/usuario <strong>{current_user.username}</strong> ({current_user.email}) le ha invitado a unirse a una sesión virtual de debate o firma de documentos en Star-Doc.</p>"
            f"<div style='background-color: #f8fafc; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4f46e5;'>"
            f"<p style='margin: 5px 0;'><strong>Tema/Motivo:</strong> {payload.reason}</p>"
            f"<p style='margin: 5px 0;'><strong>Documento en discusión:</strong> {payload.document_name or 'Ninguno'}</p>"
            f"</div>"
            f"<p style='margin-bottom: 25px;'>Para unirse a la sala de videoconferencias, haga clic en el botón de abajo:</p>"
            f"<p style='text-align: center;'><a href='{local_link}' style='background-color: #4f46e5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; box-shadow: 0 4px 6px rgba(79, 70, 229, 0.15);'>Entrar a la Videollamada</a></p>"
            f"<p style='font-size: 12px; color: #64748b; margin-top: 30px; border-top: 1px solid #e2e8f0; padding-top: 15px;'>O copie y pegue esta URL en su navegador:<br><a href='{local_link}' style='color: #4f46e5;'>{local_link}</a></p>"
            f"<p style='font-size: 11px; color: #94a3b8;'>Este sistema utiliza Jitsi Meet e integra cadena de custodia criptográfica en IPFS mediante Star-Doc.</p>"
            f"</div>"
        )
        
        for email in payload.emails:
            if email.strip():
                try:
                    await send_email_async(subject, email.strip(), body)
                    invitation_success.append(email.strip())
                except Exception as e:
                    logger.error(f"Error enviando correo de invitación a {email}: {e}")
                    
    return {
        "success": True,
        "meeting_url": meeting_info["url"],
        "room_name": room_name,
        "local_meeting_link": f"{base_url}/dashboard/reunion/{room_name}?doc={payload.document_name or ''}&token={appointment.confirmation_token}",
        "invited_emails": payload.emails,
        "invitations_sent_to": invitation_success
    }


class LiveSignaturePayload(BaseModel):
    document_filename: str
    signature_base64: str
    signer_name: str
    signer_email: Optional[str] = None
    room_name: Optional[str] = None


@router.post("/stamp-live-signature")
async def stamp_live_signature(
    payload: LiveSignaturePayload,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_session)
):
    """
    Estampa en caliente la firma caligráfica obtenida en el modal de la sala virtual directamente en el PDF activo,
    integrándolo con el flujo SignatureRequest para postergar el sellado IPFS hasta completarse todos los firmantes.
    """
    from datetime import datetime
    import tempfile
    import base64
    import fitz
    from app.models.signature import SignatureRequest
    from app.services.signature_service import SignatureService
    from app.services.ipfs_integration_service import IPFSIntegrationService
    from app.services.crypto_engine import DocClassification
    
    logger.info(f"Recibiendo firma en vivo para estampar en: {payload.document_filename}")
    
    client_ip = request.client.host if request.client else "127.0.0.1"
    real_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or client_ip
    user_agent = request.headers.get("User-Agent", "Desconocido")
    
    try:
        # 1. Sanitizar el nombre del archivo
        safe_name = os.path.basename(payload.document_filename)
        clean_name = safe_name
        if clean_name.startswith("SIGNED_"):
            clean_name = clean_name.replace("SIGNED_", "", 1)
            
        # 2. Buscar si existe una solicitud de firma activa asociada a este documento
        stmt_sig = select(SignatureRequest).where(
            SignatureRequest.document_filename == clean_name,
            SignatureRequest.status != "completed",
            SignatureRequest.status != "expired"
        )
        res_sig = await db.execute(stmt_sig)
        sig_req = res_sig.scalars().first()
        
        if sig_req:
            # Flujo unificado con SignatureRequest y SignatureSigner
            from app.models.signature import SignatureSigner
            from app.services.signature_service import encrypt_signature_base64
            
            # Cargar firmantes asociados
            stmt_signers = select(SignatureSigner).where(SignatureSigner.signature_request_id == sig_req.id)
            res_signers = await db.execute(stmt_signers)
            db_signers = res_signers.scalars().all()
            
            signer_found = None
            email_to_match = (payload.signer_email or (current_user.email if current_user else None) or "").strip().lower()
            
            for s in db_signers:
                is_match = False
                if email_to_match and s.email.lower() == email_to_match:
                    is_match = True
                elif s.name.lower() == payload.signer_name.lower():
                    is_match = True
                    
                if is_match and not s.signed:
                    signer_found = s
                    break
                    
            if signer_found:
                # Cifrar la firma manuscrita para base de datos
                encrypted_signature = encrypt_signature_base64(payload.signature_base64)
                
                signer_found.signed = True
                signer_found.signed_at = datetime.utcnow()
                signer_found.ip = real_ip
                signer_found.user_agent = user_agent
                signer_found.signature_image_encrypted = encrypted_signature
                signer_found.consent_electronic_signature = True
                signer_found.consent_habeas_data = True
                
                sig_req.status = "in_progress"
                db.add(signer_found)
                db.add(sig_req)
                await db.commit()
                
                # Consolidar en caliente las firmas en el PDF (genera SIGNED_...)
                pdf_filename = await SignatureService._consolidate_signatures(sig_req, db)
                
                # Verificar si todos han firmado cargando firmantes frescos
                stmt_fresh = select(SignatureSigner).where(SignatureSigner.signature_request_id == sig_req.id)
                res_fresh = await db.execute(stmt_fresh)
                fresh_signers = res_fresh.scalars().all()
                all_signed = all(s.signed for s in fresh_signers)
                
                if all_signed:
                    pdf_path = os.path.join(settings.OUTPUT_DIR, pdf_filename)
                    
                    try:
                        from app.services.timestamp_service import TimestampService
                        await TimestampService.stamp_file(pdf_path)
                    except Exception as ts_err:
                        logger.error(f"Error al generar sello de tiempo en sala: {ts_err}")
                        
                    doc_class = sig_req.classification or "chain_of_custody"
                    
                    if "_local" in doc_class:
                        logger.info("IPFS deshabilitado para esta firma de documento en sala.")
                        # Simulamos un doc_record local sin anclaje a IPFS
                        from unittest.mock import MagicMock
                        doc_record = MagicMock()
                        doc_record.ipfs_cid = "local"
                        
                        sha256_hash = hashlib.sha256()
                        with open(pdf_path, "rb") as f_hash:
                            for byte_block in iter(lambda: f_hash.read(4096), b""):
                                sha256_hash.update(byte_block)
                        doc_record.sha256_original = sha256_hash.hexdigest()
                        audit_cid = "local_audit"
                    else:
                        doc_record = await IPFSIntegrationService.anchor_and_stamp(
                            file_path=pdf_path,
                            classification=DocClassification(doc_class),
                            user_id=sig_req.user_id,
                            session=db,
                            signature_request_id=sig_req.id
                        )
                        # Generar Bitácora de Auditoría estructurada y anclarla a IPFS
                        audit_cid = await SignatureService.generate_and_anchor_audit_trail(sig_req.id, db)
                        logger.info(f"Bitácora de auditoría en sala anclada en IPFS con CID: {audit_cid}")
                    
                    sig_req.status = "completed"
                    sig_req.signed_document_cid = doc_record.ipfs_cid
                    sig_req.sha256_signed = doc_record.sha256_original
                    db.add(sig_req)
                    
                    # PURGAR FIRMAS MANUSCRITAS DE LA BASE DE DATOS (Privacy by Design)
                    for s in fresh_signers:
                        s.signature_image_encrypted = None
                        db.add(s)
                        
                    await db.commit()
                    
                    # Enviar el documento firmado por correo a todos los firmantes
                    try:
                        from app.services.email import EmailService
                        
                        # URL de descarga
                        download_url = f"{settings.BASE_URL}/api/documents/download/{pdf_filename}"
                        
                        for signer in fresh_signers:
                            if signer.email:
                                logger.info(f"Enviando notificación de documento firmado a {signer.email}")
                                await EmailService.send_document_signed_email_custom(
                                    recipient_email=signer.email,
                                    recipient_name=signer.name,
                                    document_name=sig_req.document_filename,
                                    download_url=download_url,
                                    sha256_val=doc_record.sha256_original,
                                    ipfs_cid=doc_record.ipfs_cid
                                )
                    except Exception as mail_err:
                        logger.error(f"Error enviando notificaciones de documento firmado por correo: {mail_err}")
                    
                    return {
                        "success": True,
                        "completed": True,
                        "message": "Firma en sala registrada. Documento completado y sellado en IPFS.",
                        "ipfs_cid": doc_record.ipfs_cid,
                        "filename": pdf_filename
                    }
                else:
                    return {
                        "success": True,
                        "completed": False,
                        "message": "Firma en sala registrada exitosamente. Pendiente por las demás firmas.",
                        "filename": pdf_filename
                    }
            
        # --- Fallback Libre (Si no existe SignatureRequest activa) ---
        pdf_path = os.path.join(settings.OUTPUT_DIR, safe_name)
        if not os.path.exists(pdf_path):
            # Intentar fallback con clean_name
            pdf_path = os.path.join(settings.OUTPUT_DIR, clean_name)
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=404, detail="El documento especificado no se encuentra.")
            
        # Decodificar firma base64
        if "," not in payload.signature_base64:
            raise HTTPException(status_code=400, detail="Firma base64 con formato inválido.")
            
        img_data = base64.b64decode(payload.signature_base64.split(",")[1])
        
        # Estampar la firma en el PDF usando PyMuPDF
        doc = fitz.open(pdf_path)
        try:
            last_page = doc[-1]
            page_text = last_page.get_text()
            is_signature_page = "ANEXO DE FIRMAS EN SALA VIRTUAL" in page_text
            
            page_width = last_page.rect.width
            page_height = last_page.rect.height
            box_height = 95
            spacing = 15
            
            if is_signature_page:
                num_signatures = page_text.count("Firmante:")
                y_offset = 100 + num_signatures * (box_height + spacing)
                if y_offset + box_height > page_height - 50:
                    last_page = doc.new_page()
                    page_width = last_page.rect.width
                    page_height = last_page.rect.height
                    last_page.draw_rect(fitz.Rect(20, 20, page_width - 20, 75), color=None, fill=(0.01, 0.24, 0.43), overlay=True)
                    last_page.insert_textbox(
                        fitz.Rect(30, 25, page_width - 30, 70),
                        "ANEXO DE FIRMAS EN SALA VIRTUAL (CONTINUACIÓN)\nSTAR-DOC",
                        fontsize=11, fontname="Helvetica-Bold", color=(1, 1, 1), align=fitz.TEXT_ALIGN_CENTER
                    )
                    y_offset = 100
            else:
                last_page = doc.new_page()
                page_width = last_page.rect.width
                page_height = last_page.rect.height
                last_page.draw_rect(fitz.Rect(20, 20, page_width - 20, 75), color=None, fill=(0.01, 0.24, 0.43), overlay=True)
                last_page.insert_textbox(
                    fitz.Rect(30, 25, page_width - 30, 70),
                    "ANEXO DE FIRMAS EN SALA VIRTUAL\nSTAR-DOC LEGALTECH PLATFORM",
                    fontsize=12, fontname="Helvetica-Bold", color=(1, 1, 1), align=fitz.TEXT_ALIGN_CENTER
                )
                y_offset = 100
                
            box_rect = fitz.Rect(20, y_offset, page_width - 20, y_offset + box_height)
            last_page.draw_rect(box_rect, color=(0.85, 0.85, 0.85), width=1)
            
            last_page.draw_rect(fitz.Rect(page_width - 150, y_offset + 5, page_width - 25, y_offset + 22), color=None, fill=(0.8, 0.95, 0.8), overlay=True)
            last_page.insert_textbox(
                fitz.Rect(page_width - 150, y_offset + 8, page_width - 25, y_offset + 20),
                "FIRMADO EN SALA ✅",
                fontsize=7, fontname="Helvetica-Bold", color=(0.1, 0.5, 0.1), align=fitz.TEXT_ALIGN_CENTER
            )
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                tmp_img.write(img_data)
                tmp_img_path = tmp_img.name
                
            img_rect = fitz.Rect(30, y_offset + 10, 160, y_offset + box_height - 10)
            last_page.insert_image(img_rect, filename=tmp_img_path)
            os.remove(tmp_img_path)
            
            from datetime import timedelta
            colombia_now = datetime.utcnow() - timedelta(hours=5)
            meta_text = (
                f"Firmante: {payload.signer_name}\n"
                f"Metodo: Firma Caligrafica en Negociacion Virtual\n"
                f"Fecha/Hora: {colombia_now.strftime('%Y-%m-%d %H:%M:%S COT')}\n"
                f"Direccion IP: {real_ip}\n"
                f"Validado por: Star-Doc LegalTech Platform"
            )
            
            last_page.insert_textbox(
                fitz.Rect(180, y_offset + 12, page_width - 160, y_offset + box_height - 5),
                meta_text, fontsize=7.5, fontname="Helvetica", color=(0.2, 0.2, 0.2)
            )
            
            # Guardar con el prefijo SIGNED_ para mantener consistencia
            out_filename = safe_name if safe_name.startswith("SIGNED_") else f"SIGNED_{safe_name}"
            out_pdf_path = os.path.join(settings.OUTPUT_DIR, out_filename)
            temp_save = f"{out_pdf_path}.tmp"
            doc.save(temp_save)
            doc.close()
            os.replace(temp_save, out_pdf_path)
        except Exception as stamp_err:
            if 'doc' in locals() and not doc.is_closed:
                doc.close()
            raise stamp_err
            
        # Al ser firma libre, determinamos si IPFS está deshabilitado para esta sala
        disable_ipfs = False
        if payload.room_name:
            stmt_apt = select(Appointment).where(Appointment.jitsi_room_name == payload.room_name)
            res_apt = await db.execute(stmt_apt)
            appointment = res_apt.scalars().first()
            if appointment and appointment.internal_notes and "[IPFS_DISABLED]" in appointment.internal_notes:
                disable_ipfs = True
                
        user_id = current_user.id if current_user else None
        
        if disable_ipfs:
            logger.info("IPFS deshabilitado para firma libre en esta videollamada.")
            from unittest.mock import MagicMock
            doc_record = MagicMock()
            doc_record.ipfs_cid = "local"
            sha256_hash = hashlib.sha256()
            with open(out_pdf_path, "rb") as f_hash:
                for byte_block in iter(lambda: f_hash.read(4096), b""):
                    sha256_hash.update(byte_block)
            doc_record.sha256_original = sha256_hash.hexdigest()
        else:
            doc_record = await IPFSIntegrationService.anchor_and_stamp(
                file_path=out_pdf_path,
                classification=DocClassification.CHAIN_OF_CUSTODY,
                user_id=user_id,
                session=db
            )
        
        return {
            "success": True,
            "completed": True,
            "message": "Firma manuscrita estampada exitosamente en el PDF.",
            "ipfs_cid": doc_record.ipfs_cid,
            "filename": out_filename
        }
    except Exception as e:
        logger.error(f"Error procesando firma caligrafica en sala: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Fallo al estampar firma caligrafica: {str(e)}")


@router.websocket("/ws-transcription/{room_name}")
async def websocket_transcription_endpoint(websocket: WebSocket, room_name: str):
    """
    WebSocket para recibir la transcripción de voz en tiempo real desde el cliente
    y acumularla en la base de datos de caché Redis.
    """
    await websocket.accept()
    logger.info(f"Conexión WebSocket establecida para transcripción en la sala: {room_name}")
    try:
        from app.core.redis_client import get_redis
        redis = await get_redis(db=3)
        key = f"meeting_transcription:{room_name}"
        
        while True:
            data = await websocket.receive_text()
            if data:
                formatted_chunk = f"{data.strip()}\n"
                await redis.append(key, formatted_chunk)
                await redis.expire(key, 86400)  # Expira en 24 horas
                await websocket.send_text("ack")
    except WebSocketDisconnect:
        logger.info(f"Conexión WebSocket cerrada para la sala: {room_name}")
    except Exception as e:
        logger.error(f"Error en WebSocket de transcripción para la sala {room_name}: {e}")
        try:
            await websocket.close()
        except:
            pass


