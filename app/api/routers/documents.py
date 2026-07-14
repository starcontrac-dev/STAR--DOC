from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from typing import List, Dict, Any, Optional
import logging
import os

from app.database import get_session
from app.auth import get_current_user
from app.models.user import User
from app.models.user_document import UserDocument
from app.models.document_ipfs import DocumentIPFS
from app.services.files import extract_text_from_bytes
from app.services.ipfs_integration_service import IPFSIntegrationService
from app.services.crypto_engine import DocClassification
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Templates Engine"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    anchor_ipfs: bool = Form(False),
    classification: str = Form("public"),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Sube un documento, extrae el texto, y lo guarda en la bóveda RAG del usuario, opcionalmente anclándolo a IPFS.
    """
    # Validar clasificación
    try:
        doc_class = DocClassification(classification)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Clasificación inválida: '{classification}'. "
                   f"Opciones: public, confidential, chain_of_custody"
        )

    valid_extensions = {".pdf", ".txt", ".md", ".docx"}
    filename = file.filename
    ext = filename[filename.rfind("."):].lower() if "." in filename else ""
    
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail="Formato no soportado.")
    
    try:
        content_bytes = await file.read()
        
        # Extraer texto usando el mismo motor que el chat
        text = await extract_text_from_bytes(content_bytes, filename)
        
        # Truncar si es exageradamente grande
        if len(text) > 150000:
            text = text[:150000] + "\n...[TRUNCADO]"
            
        doc = UserDocument(
            user_id=current_user.id,
            filename=filename,
            content_text=text
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        
        ipfs_data = None
        if anchor_ipfs:
            # Guardar temporalmente en el directorio de salida para el estampado
            os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
            temp_path = os.path.join(settings.OUTPUT_DIR, f"temp_upload_{doc.id}_{filename}")
            with open(temp_path, "wb") as temp_file:
                temp_file.write(content_bytes)

            try:
                # Anclar y estampar
                doc_record = await IPFSIntegrationService.anchor_and_stamp(
                    file_path=temp_path,
                    classification=doc_class,
                    user_id=current_user.id,
                    session=db,
                    document_id=doc.id
                )
                ipfs_data = {
                    "cid": doc_record.ipfs_cid,
                    "classification": doc_record.classification,
                    "is_encrypted": doc_record.is_encrypted,
                    "gateway_url": doc_record.gateway_url,
                    "sha256_original": doc_record.sha256_original
                }
            finally:
                # Limpiar el archivo temporal
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar el archivo temporal de subida: {e}")
        
        return {
            "success": True, 
            "message": "Documento subido a la bóveda exitosamente.",
            "document_id": doc.id,
            "filename": doc.filename,
            "text": doc.content_text,
            "ipfs": ipfs_data
        }
        
    except Exception as e:
        logger.error(f"Error subiendo documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-documents")
async def list_my_documents(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista todos los documentos en la bóveda del usuario, incluyendo metadatos de IPFS si existen.
    """
    statement = (
        select(UserDocument, DocumentIPFS)
        .join(DocumentIPFS, UserDocument.id == DocumentIPFS.document_id, isouter=True)
        .where(UserDocument.user_id == current_user.id)
        .order_by(UserDocument.upload_date.desc())
    )
    results = await db.execute(statement)
    docs = results.all()
    response_data = []
    for user_doc, doc_ipfs in docs:
        item = {
            "id": user_doc.id, 
            "filename": user_doc.filename, 
            "upload_date": user_doc.upload_date.isoformat(),
            "preview": user_doc.content_text[:100] + "..." if len(user_doc.content_text) > 100 else user_doc.content_text,
            "status": user_doc.status,
            "comments": user_doc.comments,
            "is_collaborative": user_doc.is_collaborative,
            "cryptpad_share_url": user_doc.cryptpad_share_url,
            "ipfs": None
        }
        if doc_ipfs:
            item["ipfs"] = {
                "cid": doc_ipfs.ipfs_cid,
                "classification": doc_ipfs.classification,
                "is_encrypted": doc_ipfs.is_encrypted,
                "gateway_url": doc_ipfs.gateway_url,
                "sha256_original": doc_ipfs.sha256_original,
                "pinned_kubo": doc_ipfs.pinned_kubo,
                "pinned_pinata": doc_ipfs.pinned_pinata
            }
        response_data.append(item)
        
    return response_data


# --- WORKFLOW DE APROBACIÓN DOCUMENTAL ---
from pydantic import BaseModel
from datetime import datetime

class ReviewInput(BaseModel):
    action: str  # approve | reject
    comments: Optional[str] = None


def is_user_senior(user: User) -> bool:
    """Verifica si el usuario tiene rol Senior o Compliance o es 'starcontract'."""
    return user.username == "starcontract" or user.role in ["admin", "senior", "compliance"]


@router.get("/pending-reviews", response_model=List[Dict[str, Any]])
async def list_pending_reviews(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Lista todos los documentos pendientes de revisión (Solo para revisores Senior).
    """
    if not is_user_senior(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Operación reservada exclusivamente para revisores Senior o Compliance."
        )

    statement = (
        select(UserDocument)
        .where(UserDocument.status == "pending_approval")
        .order_by(UserDocument.upload_date.desc())
    )
    results = await db.execute(statement)
    docs = results.scalars().all()
    
    return [
        {
            "id": d.id,
            "user_id": d.user_id,
            "filename": d.filename,
            "upload_date": d.upload_date.isoformat(),
            "status": d.status,
            "preview": d.content_text[:120] + "..." if len(d.content_text) > 120 else d.content_text
        }
        for d in docs
    ]


@router.post("/{doc_id}/submit-approval")
async def submit_document_for_approval(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Junior solicita la aprobación formal del documento antes de poder ser firmado.
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Documento no encontrado o sin acceso.")

    if doc.status == "approved":
        raise HTTPException(status_code=400, detail="Este documento ya ha sido aprobado.")
        
    doc.status = "pending_approval"
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    
    return {
        "success": True,
        "message": "Documento enviado con éxito para revisión del equipo Senior.",
        "status": doc.status
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene el contenido completo de un documento específico de la bóveda.
    Los usuarios Senior/Admin pueden acceder a cualquier documento para auditoría.
    Los usuarios normales solo pueden ver sus propios documentos.
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    # Permitir acceso si es el dueño O si es un revisor Senior/Admin
    if doc.user_id != current_user.id and not is_user_senior(current_user):
        raise HTTPException(status_code=403, detail="Sin permisos para acceder a este documento.")

    # Obtener el nombre del autor del documento
    author_name = None
    if doc.user_id != current_user.id:
        author = await db.get(User, doc.user_id)
        author_name = author.username if author else "Desconocido"

    return {
        "id": doc.id,
        "filename": doc.filename,
        "content_text": doc.content_text,
        "upload_date": doc.upload_date.isoformat(),
        "status": doc.status,
        "comments": doc.comments,
        "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "reviewed_by_id": doc.reviewed_by_id,
        "user_id": doc.user_id,
        "author_name": author_name,
        "is_collaborative": doc.is_collaborative,
        "cryptpad_share_url": doc.cryptpad_share_url
    }

@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Elimina un documento de la bóveda del usuario.
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Documento no encontrado o sin acceso.")
        
    await db.delete(doc)
    await db.commit()
    
    return {"success": True, "message": "Documento borrado exitosamente"}


async def auditoria_masiva_task(user_id: int):
    """
    Background Task para analizar masivamente la bóveda RAG del usuario.
    Simula la creación de un reporte de cumplimiento global usando NLP.
    """
    logger.info(f"🚀 Iniciando Auditoría Masiva en Background para usuario {user_id}")
    try:
        from app.database import async_session_maker
        from app.core.tools.analizador_documentos import analizar_contrato
        
        async with async_session_maker() as session:
            stmt = select(UserDocument).where(UserDocument.user_id == user_id)
            resultados = await session.execute(stmt)
            docs = resultados.scalars().all()
            
            reporte_global = {
                "documentos_analizados": len(docs),
                "riesgos_altos": 0,
                "score_promedio": 0
            }
            
            suma_scores = 0
            for doc in docs:
                if len(doc.content_text) > 50:
                    analisis = await analizar_contrato(texto=doc.content_text)
                    reporte_global["riesgos_altos"] += analisis.get("resumen_riesgos", {}).get("altos", 0)
                    suma_scores += analisis.get("salud_contractual", {}).get("score", 0)
            
            if len(docs) > 0:
                reporte_global["score_promedio"] = round(suma_scores / len(docs), 1)
                
            logger.info(f"✅ Auditoría Masiva Finalizada para {user_id}: {reporte_global}")
            # NOTA: Aquí se podría guardar el reporte en la base de datos o enviar un email al usuario.
            
    except Exception as e:
        logger.error(f"❌ Error en auditoría masiva para {user_id}: {e}")

@router.post("/auditoria-masiva")
async def ejecutar_auditoria_masiva(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Endpoint de Análisis Masivo (Roadmap Fase 5).
    Inicia un análisis en segundo plano de todos los documentos en la Bóveda RAG del usuario.
    """
    background_tasks.add_task(auditoria_masiva_task, current_user.id)
    return {
        "success": True, 
        "message": "La auditoría masiva ha comenzado en segundo plano. Te notificaremos cuando esté lista."
    }



@router.post("/{doc_id}/review")
async def review_document(
    doc_id: int,
    payload: ReviewInput,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Un revisor Senior aprueba o rechaza un borrador de documento.
    """
    if not is_user_senior(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Operación reservada exclusivamente para revisores Senior o Compliance."
        )

    doc = await db.get(UserDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    action = payload.action.strip().lower()
    if action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Acción inválida. Use 'approve' o 'reject'.")

    if action == "reject" and (not payload.comments or not payload.comments.strip()):
        raise HTTPException(
            status_code=400, 
            detail="Debe incluir obligatoriamente comentarios justificando los motivos del rechazo."
        )

    # Actualizar estado
    if action == "approve":
        doc.status = "approved"
        doc.comments = payload.comments
    else:
        doc.status = "rejected"
        doc.comments = payload.comments

    doc.reviewed_by_id = current_user.id
    doc.reviewed_at = datetime.utcnow()
    
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "success": True,
        "message": f"El documento ha sido {doc.status} exitosamente.",
        "status": doc.status,
        "comments": doc.comments
    }


# --- ENDPOINTS DE EDICIÓN COLABORATIVA CON CRYPTPAD.FR (NUBE) ---

class LinkCollaborativeInput(BaseModel):
    cryptpad_url: str
    collaborator_emails: Optional[List[str]] = None
    custom_message: Optional[str] = None

@router.post("/{doc_id}/start-collaborative")
async def start_collaborative(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Inicia la co-edición en la nube para un documento. Retorna la URL de CryptPad adecuada
    según la extensión del archivo (.md o .docx).
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Documento no encontrado o sin acceso.")

    # Validar formato
    ext = os.path.splitext(doc.filename)[1].lower()
    if ext not in [".md", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail=f"La co-edición colaborativa no es compatible con el formato '{ext}'. Solo se admiten archivos .md y .docx"
        )

    # Determinar URL inicial de CryptPad.fr (Zero-Knowledge OnlyOffice para Word)
    if ext == ".md":
        cryptpad_url = "https://cryptpad.fr/pad/"
    else:
        cryptpad_url = "https://cryptpad.fr/doc/"

    return {
        "success": True,
        "cryptpad_init_url": cryptpad_url,
        "extension": ext,
        "filename": doc.filename,
        "content_text": doc.content_text
    }


@router.post("/{doc_id}/link-collaborative")
async def link_collaborative(
    doc_id: int,
    payload: LinkCollaborativeInput,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Vincula la URL de la sala de CryptPad creada al documento en STAR-DOC, activa el estado colaborativo,
    y despacha invitaciones formales por correo electrónico a los colaboradores interesados.
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Documento no encontrado o sin acceso.")

    url = payload.cryptpad_url.strip()
    # Validación de seguridad: debe ser un enlace de cryptpad.fr
    if not url.startswith("https://cryptpad.fr/"):
        raise HTTPException(
            status_code=400,
            detail="URL no válida. Por motivos de seguridad y privacidad (Zero-Knowledge), la sala colaborativa debe estar alojada en la plataforma oficial de https://cryptpad.fr."
        )

    doc.cryptpad_share_url = url
    doc.is_collaborative = True
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    # Enviar invitaciones por correo electrónico a colaboradores si se suministran
    emails_sent = []
    if payload.collaborator_emails:
        from app.services.email import EmailService
        from app.services.signature_service import validate_signer_email_robust
        
        for email in payload.collaborator_emails:
            email = email.strip()
            if not email:
                continue
            # Validar correo
            email_valido, normalized_email = await validate_signer_email_robust(email)
            if email_valido:
                background_tasks.add_task(
                    EmailService.send_collaborative_invitation,
                    recipient_email=normalized_email,
                    document_name=doc.filename,
                    colab_url=url,
                    sender_name=current_user.username,
                    custom_message=payload.custom_message
                )
                emails_sent.append(normalized_email)
            else:
                logger.warning(f"Correo de colaborador omitido por no ser válido: {email}")

    msg = "Enlace colaborativo de CryptPad vinculado correctamente y estado activado."
    if emails_sent:
        msg += f" Se despacharon invitaciones de co-edición por correo electrónico a: {', '.join(emails_sent)}"

    return {
        "success": True,
        "message": msg,
        "is_collaborative": doc.is_collaborative,
        "cryptpad_share_url": doc.cryptpad_share_url,
        "invited_collaborators": emails_sent
    }


@router.post("/{doc_id}/finalize-collaborative")
async def finalize_collaborative(
    doc_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """
    Recibe el archivo final consolidado exportado desde CryptPad.fr, actualiza el contenido
    de texto en base de datos para RAG, guarda el archivo físico convertido a PDF en settings.OUTPUT_DIR,
    reinicia el estado del workflow a 'draft' y desactiva el estado colaborativo.
    """
    doc = await db.get(UserDocument, doc_id)
    if not doc or doc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Documento no encontrado o sin acceso.")

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower() if "." in filename else ""
    if ext not in [".md", ".docx"]:
        raise HTTPException(
            status_code=400,
            detail="Formato del archivo de consolidación no soportado. Debe ser .md o .docx descargado de CryptPad."
        )

    try:
        content_bytes = await file.read()
        
        # 1. Extraer texto para actualizar la bóveda de conocimiento (RAG)
        text = await extract_text_from_bytes(content_bytes, filename)
        if len(text) > 150000:
            text = text[:150000] + "\n...[TRUNCADO]"

        # Asegurar que el directorio de salida existe
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        
        # 2. Definir nombres y rutas para guardar el archivo exportado y el PDF resultante
        base_name = f"doc_colab_{doc.id}"
        temp_input_name = f"{base_name}{ext}"
        temp_input_path = os.path.join(settings.OUTPUT_DIR, temp_input_name)
        
        # Guardar archivo original subido (.md o .docx)
        with open(temp_input_path, "wb") as f_in:
            f_in.write(content_bytes)

        # 3. Conversión de formato a PDF para posibilitar firmas electrónicas en el flujo
        pdf_path = None
        from app.services.document_service import convert_md_to_pdf, convert_to_pdf
        
        if ext == ".md":
            pdf_path = await convert_md_to_pdf(temp_input_path, settings.OUTPUT_DIR)
            # Limpiar archivo markdown temporal
            if os.path.exists(temp_input_path):
                try:
                    os.remove(temp_input_path)
                except Exception as e_rm:
                    logger.warning(f"No se pudo remover markdown temporal: {e_rm}")
        else:  # .docx
            pdf_path = await convert_to_pdf(temp_input_path, settings.OUTPUT_DIR)
            # No removemos el .docx inmediatamente por si LibreOffice o docx2pdf requirieron retención,
            # pero podemos limpiarlo si el PDF se creó con éxito
            if pdf_path and os.path.exists(temp_input_path):
                try:
                    os.remove(temp_input_path)
                except Exception as e_rm:
                    logger.warning(f"No se pudo remover docx temporal: {e_rm}")

        if not pdf_path or not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=500,
                detail="Fallo en la conversión interna del archivo de co-edición a formato PDF. Verifique motores de renderizado."
            )

        pdf_filename = os.path.basename(pdf_path)

        # 4. Actualizar el registro en base de datos
        doc.content_text = text
        doc.filename = pdf_filename  # Ahora apunta al PDF generado en OUTPUT_DIR para firmas
        doc.is_collaborative = False
        doc.status = "draft"  # Vuelve a borrador limpio para workflow de aprobación/firma
        
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        return {
            "success": True,
            "message": "Co-edición en tiempo real finalizada con éxito. Documento consolidado en PDF y listo para aprobación.",
            "document_id": doc.id,
            "filename": doc.filename,
            "is_collaborative": doc.is_collaborative
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error finalizando colaboración en documento {doc_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error del servidor al finalizar colaboración: {str(e)}"
        )
