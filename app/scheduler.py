from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
import os
import logging
from typing import Dict, Any

# --- Local Application Imports ---
# En el futuro, aquí importaremos la lógica de generación de documentos refactorizada.
# from app.main import generate_document_logic

logger = logging.getLogger(__name__)

# Cargar la URL de la base de datos desde las variables de entorno
DATABASE_URL = os.getenv("DATABASE_URL")

# Configurar el jobstore para usar SQLAlchemy con nuestra base de datos PostgreSQL
jobstores = {
    'default': SQLAlchemyJobStore(url=DATABASE_URL)
}

# Crear una instancia del scheduler que se utilizará en toda la aplicación
scheduler = AsyncIOScheduler(jobstores=jobstores)

async def _execute_document_generation_task(template_name: str, context: Dict[str, Any], output_format: str, user_id: str, google_doc_id: str = None):
    """
    Función que ejecuta la lógica de generación de documentos.
    Esta es la función que el scheduler llamará en el momento programado.
    """
    # Importación local para evitar dependencias circulares
    from app.services.document_service import internal_generate_document

    logger.info(f"Ejecutando tarea programada para el usuario '{user_id}'.")

    try:
        # Determinar el nombre del template para logging
        doc_identifier = template_name or google_doc_id

        # Llamar a la lógica de generación de documentos refactorizada
        output_filename = await internal_generate_document(
            template_filename=template_name,
            context=context,
            output_format=output_format,
            google_doc_id=google_doc_id
        )
        logger.info(f"Tarea completada. Documento generado: {output_filename}")
    except Exception as e:
        logger.error(f"Falló la ejecución de la tarea programada para el usuario '{user_id}': {e}")

def add_document_generation_job(job_id: str, template_name: str, context: Dict[str, Any], output_format: str, user_id: str, cron_expression: str, google_doc_id: str = None):
    """
    Añade una nueva tarea de generación de documentos al scheduler.
    """
    try:
        trigger = CronTrigger.from_crontab(cron_expression)
        job = scheduler.add_job(
            _execute_document_generation_task,
            trigger=trigger,
            args=[template_name, context, output_format, user_id, google_doc_id],
            id=job_id,
            name=f"Generar {template_name or google_doc_id} para {user_id}",
            replace_existing=True
        )
        logger.info(f"Tarea '{job_id}' programada para el usuario '{user_id}' con la expresión cron: '{cron_expression}'.")
        return job
    except Exception as e:
        logger.error(f"Error al programar la tarea '{job_id}': {e}")
        raise

async def _execute_ipns_republish_task():
    """
    Tarea periódica para republicar todas las claves IPNS en Kubo.
    """
    from app.database import async_session_maker
    from app.services.ipns_republisher_service import republish_all_ipns_keys
    
    logger.info("Iniciando tarea programada de republicación de claves IPNS.")
    try:
        async with async_session_maker() as session:
            result = await republish_all_ipns_keys(session)
            logger.info(f"Tarea de republicación IPNS completada: {result}")
    except Exception as e:
        logger.error(f"Error en la tarea programada de republicación IPNS: {e}")

async def _execute_check_expiring_documents_task():
    """
    Tarea diaria para revisar documentos por expirar y enviar notificaciones.
    """
    from app.database import async_session_maker
    from app.models.user_document import UserDocument
    from app.models.user import User
    from app.services.email import EmailService
    from sqlmodel import select
    from datetime import datetime
    
    logger.info("Iniciando revisión de documentos por expirar.")
    try:
        async with async_session_maker() as session:
            # Consultamos todos los UserDocument que tienen metadatos
            result = await session.execute(select(UserDocument).where(UserDocument.metadata_json != None))
            docs = result.scalars().all()
            
            for doc in docs:
                metadata = doc.metadata_json
                if not metadata or "expiration_date" not in metadata:
                    continue
                
                exp_date_str = metadata["expiration_date"]
                try:
                    # Formato YYYY-MM-DD
                    exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                except Exception:
                    continue
                
                today = datetime.utcnow().date()
                days_left = (exp_date - today).days
                
                # Enviamos alertas exactamente a los 30, 15, 7 o 1 día antes del vencimiento
                if days_left in [30, 15, 7, 1]:
                    # Obtener el abogado
                    user_res = await session.execute(select(User).where(User.id == doc.user_id))
                    user = user_res.scalars().first()
                    if user:
                        client_name = metadata.get("client_name") or metadata.get("name") or "Cliente"
                        await EmailService.send_document_expiration_alert(
                            lawyer_email=user.email,
                            document_name=doc.filename,
                            client_name=client_name,
                            expiration_date=exp_date_str,
                            days_left=days_left
                        )
                        logger.info(f"Alerta de vencimiento enviada a {user.email} para el documento {doc.filename}")
    except Exception as e:
        logger.error(f"Error en la tarea programada de revisión de vencimientos: {e}")

async def _execute_ipfs_retry_task():
    """
    Tarea periódica para procesar e intentar subir archivos fallidos de IPFS.
    Reintenta hasta 3 veces antes de marcar como definitivamente fallido.
    """
    from app.database import async_session_maker
    from app.models.ipfs_pending_task import IPFSPendingTask
    from app.models.document_ipfs import DocumentIPFS
    from app.models.signature import SignatureRequest
    from app.services.ipfs_service import IPFSService
    from app.services.crypto_engine import CryptoEngine, DocClassification
    from app.services.email import EmailService
    from app.core.config import settings
    from sqlmodel import select
    from datetime import datetime
    import os
    import hashlib
    import mimetypes
    
    logger.debug("Iniciando tarea programada de procesamiento de cola de reintentos IPFS...")
    
    try:
        async with async_session_maker() as session:
            # 1. Buscar todas las tareas pendientes
            stmt = select(IPFSPendingTask).where(IPFSPendingTask.status == "pending")
            res = await session.execute(stmt)
            tasks = res.scalars().all()
            
            if not tasks:
                logger.debug("No hay tareas pendientes en la cola de IPFS.")
                return
                
            for task in tasks:
                logger.info(f"Procesando reintento de IPFS para la tarea ID={task.id}, archivo: {task.file_path}")
                
                # Marcar como en proceso
                task.status = "processing"
                task.updated_at = datetime.utcnow()
                session.add(task)
                await session.commit()
                
                # Validar existencia del archivo
                if not os.path.exists(task.file_path):
                    task.status = "failed"
                    task.last_error = "El archivo físico local no existe en el disco."
                    task.updated_at = datetime.utcnow()
                    session.add(task)
                    await session.commit()
                    logger.error(f"Fallo en tarea IPFS ID={task.id}: Archivo no encontrado.")
                    continue
                    
                try:
                    # Cargar el archivo y calcular metadatos
                    filename = os.path.basename(task.file_path)
                    with open(task.file_path, "rb") as f:
                        file_data = f.read()
                    
                    sha256_original = hashlib.sha256(file_data).hexdigest()
                    file_size_stamped = os.path.getsize(task.file_path)
                    
                    classification_enum = DocClassification(task.classification)
                    
                    # Generar llave de encriptación compartida si aplica
                    encryption_key = None
                    if classification_enum != DocClassification.PUBLIC:
                        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                        encryption_key = AESGCM.generate_key(bit_length=256)
                    
                    # Subir de forma segura a IPFS
                    result = await IPFSService.secure_upload(
                        file_name=filename,
                        file_data=file_data,
                        classification=classification_enum,
                        encryption_key=encryption_key,
                        metadata={
                            "source": "star-doc-generator-retry-queue",
                            "user_id": str(task.user_id),
                            "sha256_original": sha256_original
                        }
                    )
                    
                    # Buscar si ya existe el registro de DocumentIPFS provisional
                    doc_ipfs_stmt = select(DocumentIPFS).where(DocumentIPFS.sha256_original == sha256_original)
                    doc_res = await session.execute(doc_ipfs_stmt)
                    doc_record = doc_res.scalars().first()
                    
                    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    
                    if doc_record:
                        # Actualizar el registro provisional existente
                        doc_record.ipfs_cid = result["cid"]
                        doc_record.file_size_bytes = file_size_stamped
                        doc_record.mime_type = mime
                        doc_record.pinned_kubo = result.get("kubo") is not None
                        doc_record.pinned_pinata = result.get("pinata") is not None
                        doc_record.gateway_url = result.get("gateway_url")
                        doc_record.verified_at = datetime.utcnow()
                        
                        if result.get("encryption_key") and task.user_id:
                            doc_record.encryption_key_encrypted = CryptoEngine.encrypt_document_key(
                                result["encryption_key"], task.user_id
                            )
                        session.add(doc_record)
                    else:
                        # Crear nuevo registro si no existía (fallback de seguridad)
                        doc_record = DocumentIPFS(
                            document_id=task.document_id,
                            user_id=task.user_id,
                            ipfs_cid=result["cid"],
                            ipfs_cid_original=result["cid"],
                            sha256_original=sha256_original,
                            classification=task.classification,
                            is_encrypted=result["is_encrypted"],
                            original_filename=filename,
                            file_size_bytes=file_size_stamped,
                            mime_type=mime,
                            pinned_kubo=result.get("kubo") is not None,
                            pinned_pinata=result.get("pinata") is not None,
                            gateway_url=result.get("gateway_url"),
                            verified_at=datetime.utcnow()
                        )
                        if result.get("encryption_key") and task.user_id:
                            doc_record.encryption_key_encrypted = CryptoEngine.encrypt_document_key(
                                result["encryption_key"], task.user_id
                            )
                        session.add(doc_record)
                    
                    await session.commit()
                    
                    # Si está asociada a una solicitud de firma, actualizar su CID y notificar
                    if task.signature_request_id:
                        sig_stmt = select(SignatureRequest).where(SignatureRequest.id == task.signature_request_id)
                        sig_res = await session.execute(sig_stmt)
                        sig_req = sig_res.scalars().first()
                        
                        if sig_req:
                            sig_req.signed_document_cid = result["cid"]
                            sig_req.sha256_signed = sha256_original
                            sig_req.status = "completed"
                            session.add(sig_req)
                            await session.commit()
                            
                            # Enviar alertas por correo con token de descarga público
                            from app.auth import create_file_download_token
                            download_token = create_file_download_token(filename, sig_req.user_id)
                            download_url = f"{settings.BASE_URL}/files/{filename}?token={download_token}"
                            signed_by_names = ", ".join(s["name"] for s in sig_req.signers)
                            
                            # Al abogado
                            from app.models.user import User
                            lawyer_stmt = select(User).where(User.id == sig_req.user_id)
                            lawyer_res = await session.execute(lawyer_stmt)
                            lawyer = lawyer_res.scalars().first()
                            if lawyer:
                                await EmailService.send_document_signed_alert(
                                    recipient_email=lawyer.email,
                                    document_name=filename,
                                    signed_by=signed_by_names,
                                    download_url=download_url,
                                    ipfs_cid=result["cid"]
                                )
                                
                            # A los firmantes
                            for s in sig_req.signers:
                                await EmailService.send_document_signed_alert(
                                    recipient_email=s["email"],
                                    document_name=filename,
                                    signed_by=signed_by_names,
                                    download_url=download_url,
                                    ipfs_cid=result["cid"]
                                )
                                
                    # Marcar tarea como completada
                    task.status = "completed"
                    task.updated_at = datetime.utcnow()
                    session.add(task)
                    await session.commit()
                    logger.info(f"Tarea de reintento IPFS ID={task.id} completada exitosamente. CID: {result['cid']}")
                    
                    # Eliminar copia temporal de reintentos
                    if "ipfs_pending" in task.file_path and os.path.exists(task.file_path):
                        try:
                            os.remove(task.file_path)
                            logger.info(f"Archivo temporal de reintentos eliminado tras éxito: {task.file_path}")
                        except Exception as rm_err:
                            logger.warning(f"No se pudo eliminar el archivo temporal de reintentos {task.file_path}: {rm_err}")
                    
                except Exception as e:
                    logger.error(f"Error procesando reintento IPFS para tarea ID={task.id}: {e}")
                    task.retry_count += 1
                    task.last_error = str(e)
                    if task.retry_count >= task.max_retries:
                        task.status = "failed"
                        logger.error(f"La tarea de IPFS ID={task.id} ha fallado tras {task.max_retries} intentos.")
                        
                        # Eliminar copia temporal si falla definitivamente para no consumir espacio
                        if "ipfs_pending" in task.file_path and os.path.exists(task.file_path):
                            try:
                                os.remove(task.file_path)
                                logger.info(f"Archivo temporal de reintentos eliminado tras fallo definitivo: {task.file_path}")
                            except Exception as rm_err:
                                logger.warning(f"No se pudo eliminar el archivo temporal fallido {task.file_path}: {rm_err}")
                    else:
                        task.status = "pending" # Volver a encolar
                    task.updated_at = datetime.utcnow()
                    session.add(task)
                    await session.commit()
    except Exception as general_err:
        logger.error(f"Excepcion en _execute_ipfs_retry_task: {general_err}")

# Función para iniciar el scheduler
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler iniciado...")
        
        # Programar reintentos de IPFS cada 1 hora
        try:
            scheduler.add_job(
                _execute_ipfs_retry_task,
                trigger=CronTrigger(hour="*"),
                id="ipfs_retry_task",
                name="Procesamiento de cola de reintentos IPFS",
                replace_existing=True
            )
            logger.info("Tarea de reintentos IPFS programada cada 1 hora.")
        except Exception as e:
            logger.error(f"Error al programar la tarea de reintentos IPFS: {e}")

        # Programar la republicación de claves IPNS cada 3 horas
        try:
            scheduler.add_job(
                _execute_ipns_republish_task,
                trigger=CronTrigger(hour="*/3"),
                id="ipns_republish_task",
                name="Republicación automática de claves IPNS",
                replace_existing=True
            )
            logger.info("Tarea de republicación IPNS programada cada 3 horas.")
        except Exception as e:
            logger.error(f"Error al programar la tarea de republicación IPNS: {e}")

        # Programar la revisión de vencimientos todos los días a las 8:00 AM
        try:
            scheduler.add_job(
                _execute_check_expiring_documents_task,
                trigger=CronTrigger(hour=8, minute=0),
                id="check_expiring_documents_task",
                name="Revisión diaria de vencimiento de contratos",
                replace_existing=True
            )
            logger.info("Tarea de alertas de vencimiento de contratos programada a las 8:00 AM diariamente.")
        except Exception as e:
            logger.error(f"Error al programar la tarea de alertas de vencimiento: {e}")

# Función para detener el scheduler
def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler detenido.")

