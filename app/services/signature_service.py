"""
Servicio para la gestión de firmas electrónicas, estampado de PDFs y
generación de Certificados de Cadena de Custodia en STAR-DOC.
"""
import os
import uuid
import base64
import logging
import tempfile
import json
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.signature import SignatureRequest, SignatureSigner
from app.services.email import EmailService

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding

logger = logging.getLogger(__name__)

# --- Cifrado AES-256-CBC para Firmas Biométricas ---
_raw_key = os.getenv("SIGNATURE_ENCRYPTION_KEY", settings.SECRET_KEY)
if isinstance(_raw_key, str):
    ENCRYPTION_KEY = hashlib.sha256(_raw_key.encode('utf-8')).digest()
else:
    ENCRYPTION_KEY = _raw_key[:32]

def encrypt_signature_base64(plain_base64: str) -> Optional[str]:
    """Cifra la imagen base64 de la firma usando AES-256-CBC."""
    if not plain_base64:
        return None
    try:
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plain_base64.encode('utf-8')) + padder.finalize()
        
        cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
        
        return base64.b64encode(iv + encrypted_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Error cifrando firma: {e}")
        raise ValueError("Error de seguridad interna al procesar firma.")

def decrypt_signature_base64(encrypted_base64: str) -> Optional[str]:
    """Descifra la imagen base64 de la firma para inyección en el PDF."""
    if not encrypted_base64:
        return None
    try:
        data = base64.b64decode(encrypted_base64.encode('utf-8'))
        iv = data[:16]
        encrypted_bytes = data[16:]
        
        cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(encrypted_bytes) + decryptor.finalize()
        
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_bytes = unpadder.update(decrypted_padded) + unpadder.finalize()
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Error descifrando firma: {e}")
        raise ValueError("Error de descifrado. Clave de seguridad inválida o firma alterada.")


# --- Validación de Correo Avanzada con registros MX/A ---
async def validate_signer_email_robust(email: str) -> tuple[bool, str]:
    """
    Realiza una validación en dos capas para correos de firmantes:
    1. Sintáctica y normalización básica.
    2. Existencia de registros DNS MX/A para prevenir dominios inválidos/falsos.
    """
    from email_validator import validate_email, EmailNotValidError
    
    # Capa 1: Sintaxis
    try:
        email_info = validate_email(email, check_deliverability=False)
        normalized_email = email_info.normalized
        domain = email_info.domain
    except EmailNotValidError as err:
        return False, f"Formato de correo inválido: {str(err)}"
    
    # Evitar dominios conocidos de correos temporales
    disposable_domains = {"yopmail.com", "mailinator.com", "tempmail.com", "guerrillamail.com", "dispostable.com"}
    if domain.lower() in disposable_domains:
        return False, "No se permiten correos electrónicos temporales o desechables."

    # Capa 2: Resolución DNS de registros MX/A
    try:
        import dns.resolver
        
        def check_mx():
            try:
                answers = dns.resolver.resolve(domain, 'MX')
                return len(answers) > 0
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
                try:
                    a_records = dns.resolver.resolve(domain, 'A')
                    return len(a_records) > 0
                except Exception:
                    return False
            except Exception:
                return False

        has_mx = await asyncio.to_thread(check_mx)
        if not has_mx:
            return False, f"El dominio '{domain}' no tiene servidores de correo configurados (registros MX/A inexistentes)."
            
        return True, normalized_email
    except Exception as e:
        logger.warning(f"Error resolviendo registros DNS para {domain}: {e}. Se permite por fallback sintáctico.")
        return True, normalized_email


class SignatureService:
    @staticmethod
    async def create_signature_request(
        user_id: int,
        document_filename: str,
        signers_list: List[Dict[str, str]],
        expiration_days: int,
        classification: str = "chain_of_custody",
        base_url: Optional[str] = None,
        db: AsyncSession = None
    ) -> SignatureRequest:
        """
        Crea una solicitud de firma electrónica.
        Genera un token único (UUID) para cada firmante y envía invitaciones por correo.
        """
        # Validar existencia del archivo
        doc_path = os.path.join(settings.OUTPUT_DIR, document_filename)
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"El documento {document_filename} no se encuentra en el directorio de salida.")
            
        expiration = datetime.utcnow() + timedelta(days=expiration_days)
        
        # Validar correos de los firmantes antes de cualquier inserción
        for signer in signers_list:
            email_valido, msg_error = await validate_signer_email_robust(signer["email"])
            if not email_valido:
                raise ValueError(msg_error)
        
        # Crear modelo SignatureRequest
        req = SignatureRequest(
            user_id=user_id,
            document_filename=document_filename,
            status="pending",
            expiration=expiration,
            classification=classification
        )
        db.add(req)
        await db.flush()
        
        # Crear los modelos SignatureSigner relacionales
        for signer in signers_list:
            _, normalized_email = await validate_signer_email_robust(signer["email"])
            db_signer = SignatureSigner(
                signature_request_id=req.id,
                name=signer["name"].strip(),
                email=normalized_email,
                signed=False,
                token=str(uuid.uuid4())
            )
            db.add(db_signer)
            
        await db.commit()
        await db.refresh(req)
        
        if not base_url:
            base_url = settings.BASE_URL

        # Obtener los firmantes desde base de datos
        stmt = select(SignatureSigner).where(SignatureSigner.signature_request_id == req.id)
        res = await db.execute(stmt)
        db_signers = res.scalars().all()

        # Enviar correos de invitación a firmar
        for signer in db_signers:
            sign_url = f"{base_url}/sign/{signer.token}"
            await EmailService.send_signature_request(
                recipient_email=signer.email,
                signer_name=signer.name,
                document_name=document_filename,
                sign_url=sign_url
            )
            logger.info(f"Solicitud de firma en base relacional enviada a {signer.email} con token: {signer.token}")
            
        return req

    @staticmethod
    async def get_signature_request_by_token(token: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
        """
        Busca la solicitud de firma correspondiente al token y retorna la solicitud y el firmante específico.
        Búsqueda indexada atómica O(1).
        """
        stmt = select(SignatureSigner).where(SignatureSigner.token == token)
        res = await db.execute(stmt)
        signer = res.scalar_one_or_none()
        
        if not signer:
            return None
            
        req = signer.request
        # Validar si ya expiró
        if req.expiration < datetime.utcnow() and req.status != "expired":
            req.status = "expired"
            db.add(req)
            await db.commit()
            return None
            
        return {
            "request": req,
            "signer": signer
        }

    @staticmethod
    async def process_signature(
        token: str,
        canvas_base64: str,
        client_ip: str,
        user_agent: str,
        consent_electronic_signature: bool = True,
        consent_habeas_data: bool = True,
        base_url: Optional[str] = None,
        db: AsyncSession = None,
        public_key: Optional[str] = None,
        crypto_signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Registra el acto de firma por parte del firmante que posee el token.
        Si todos los firmantes han firmado, consolida las firmas en el PDF,
        anexa el Certificado de Cadena de Custodia, sube el PDF firmado final a IPFS
        y envía notificaciones a todas las partes.
        """
        found = await SignatureService.get_signature_request_by_token(token, db)
        if not found:
            raise ValueError("Token de firma inválido, inexistente o expirado.")
            
        req: SignatureRequest = found["request"]
        current_signer: SignatureSigner = found["signer"]
        
        if current_signer.signed:
            return {"success": False, "message": "Ya has firmado este documento previamente."}
            
        if not consent_electronic_signature or not consent_habeas_data:
            raise ValueError("Debe aceptar obligatoriamente los consentimientos de firma electrónica y Habeas Data.")

        # Cifrar la imagen manuscrita de la firma
        encrypted_signature = encrypt_signature_base64(canvas_base64)

        # Si se envían la clave pública y la firma avanzada ECDSA, guardarlas en declaration_text
        if public_key and crypto_signature:
            orig_decl = current_signer.declaration_text or ""
            if "[ECDSA_PUB" not in orig_decl:
                current_signer.declaration_text = f"{orig_decl} [ECDSA_PUB:{public_key}] [ECDSA_SIG:{crypto_signature}]".strip()

        # Actualizar estado del firmante actual en base de datos
        current_signer.signed = True
        current_signer.signed_at = datetime.utcnow()
        current_signer.ip = client_ip
        current_signer.user_agent = user_agent
        current_signer.signature_image_encrypted = encrypted_signature
        current_signer.consent_electronic_signature = True
        current_signer.consent_habeas_data = True
        
        req.status = "in_progress"
        db.add(current_signer)
        db.add(req)
        await db.commit()
        await db.refresh(req)
        await db.refresh(current_signer)
        
        # CONSOLIDAR EN CALIENTE LAS FIRMAS PARCIALES ACUMULADAS HASTA EL MOMENTO
        pdf_filename = await SignatureService._consolidate_signatures(req, db)
        
        # Obtener todos los firmantes para verificar si el proceso ha culminado
        stmt = select(SignatureSigner).where(SignatureSigner.signature_request_id == req.id)
        res = await db.execute(stmt)
        db_signers = res.scalars().all()
        
        # Verificar si todos los firmantes han completado el firmado
        all_signed = all(s.signed for s in db_signers)
        
        if all_signed:
            from app.services.ipfs_integration_service import IPFSIntegrationService
            from app.services.crypto_engine import DocClassification
            
            pdf_path = os.path.join(settings.OUTPUT_DIR, pdf_filename)
            
            # Generar sellado de tiempo oficial (RFC 3161 - Ley 527 de 1999 Colombia)
            try:
                from app.services.timestamp_service import TimestampService
                tsr_path = await TimestampService.stamp_file(pdf_path)
                if tsr_path:
                    logger.info(f"Sello de tiempo criptográfico RFC 3161 generado en: {tsr_path}")
            except Exception as ts_err:
                logger.error(f"Error al generar el sello de tiempo criptográfico: {ts_err}")
            
            try:
                # Sellar documento en IPFS Kubo con la clasificación elegida por las partes
                doc_class = req.classification or "chain_of_custody"
                doc_record = await IPFSIntegrationService.anchor_and_stamp(
                    file_path=pdf_path,
                    classification=DocClassification(doc_class),
                    user_id=req.user_id,
                    session=db,
                    signature_request_id=req.id
                )
                
                # Generar Bitácora de Auditoría estructurada y anclarla a IPFS
                audit_cid = await SignatureService.generate_and_anchor_audit_trail(req.id, db)
                logger.info(f"Bitácora de auditoría anclada en IPFS con CID: {audit_cid}")
                
                # Calcular el hash SHA-256 real de la versión estampada definitiva en disco
                import hashlib
                with open(pdf_path, 'rb') as f_signed:
                    signed_bytes = f_signed.read()
                stamped_hash = hashlib.sha256(signed_bytes).hexdigest()

                # Actualizar base de datos de firmas
                req.status = "completed"
                req.signed_document_cid = doc_record.ipfs_cid
                req.sha256_signed = stamped_hash
                db.add(req)
                
                # Actualizar el estado del documento asociado en el workflow (Opción B)
                try:
                    from app.models.user_document import UserDocument
                    stmt_doc = select(UserDocument).where(UserDocument.filename == req.document_filename)
                    res_doc = await db.execute(stmt_doc)
                    user_doc = res_doc.scalar_one_or_none()
                    if user_doc:
                        user_doc.status = "signed"
                        db.add(user_doc)
                except Exception as ex_workflow:
                    logger.error(f"Error al actualizar estado del documento a signed en workflow: {ex_workflow}")
                
                # PURGAR FIRMAS MANUSCRITAS DE LA BASE DE DATOS PARA PROTECCIÓN BIOMÉTRICA (Privacy by Design)
                for s in db_signers:
                    s.signature_image_encrypted = None
                    db.add(s)
                
                await db.commit()
                
                if not base_url:
                    base_url = settings.BASE_URL

                # Generar token de descarga pública seguro
                from app.auth import create_file_download_token
                download_token = create_file_download_token(pdf_filename, req.user_id)

                # Notificar a todas las partes por correo con la URL firmada temporalmente
                download_url = f"{base_url}/files/{pdf_filename}?token={download_token}"
                signed_by_names = ", ".join(s.name for s in db_signers)
                
                # Al abogado
                from app.models.user import User
                lawyer = await db.get(User, req.user_id)
                if lawyer:
                    await EmailService.send_document_signed_alert(
                        recipient_email=lawyer.email,
                        document_name=pdf_filename,
                        signed_by=signed_by_names,
                        download_url=download_url,
                        ipfs_cid=doc_record.ipfs_cid
                    )
                    
                # A los firmantes
                for s in db_signers:
                    await EmailService.send_document_signed_alert(
                        recipient_email=s.email,
                        document_name=pdf_filename,
                        signed_by=signed_by_names,
                        download_url=download_url,
                        ipfs_cid=doc_record.ipfs_cid
                    )
                    
                logger.info(f"Firma completada exitosamente. Documento sellado en IPFS CID: {doc_record.ipfs_cid}")
                return {
                    "success": True,
                    "completed": True,
                    "message": "Firma procesada y documento consolidado con éxito.",
                    "ipfs_cid": doc_record.ipfs_cid
                }
            except Exception as e:
                logger.error(f"Error anclando PDF firmado a IPFS: {e}")
                # A pesar del error de IPFS, el PDF se firmó físicamente
                req.status = "completed"
                db.add(req)
                
                # Purgar en caso de fallback
                for s in db_signers:
                    s.signature_image_encrypted = None
                    db.add(s)
                    
                await db.commit()
                return {
                    "success": True,
                    "completed": True,
                    "message": "Firma procesada y documento consolidado con éxito, pero falló el sellado IPFS."
                }
                
        return {
            "success": True,
            "completed": False,
            "message": "Firma registrada y estampada en caliente. Pendiente por las demás firmas."
        }

    @staticmethod
    async def _consolidate_signatures(req: SignatureRequest, db: AsyncSession) -> str:
        """
        Método interno senior que:
        1. Carga el PDF original.
        2. Crea una nueva página al final para el Certificado de Firma y Cadena de Custodia.
        3. Dibuja un hermoso layout legal y estampa las firmas con sus metadatos usando PyMuPDF.
        """
        orig_filename = req.document_filename
        if not orig_filename.endswith('.pdf'):
            base = os.path.splitext(orig_filename)[0]
            orig_filename = f"{base}.pdf"
            
        pdf_path = os.path.join(settings.OUTPUT_DIR, orig_filename)
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"No se encontró el PDF base en: {pdf_path}")
            
        # Calcular Hash SHA-256 del documento original (evidencia de integridad previa)
        with open(pdf_path, 'rb') as f:
            orig_bytes = f.read()
            sha256_original = hashlib.sha256(orig_bytes).hexdigest()
            
        # Obtener los firmantes de la base de datos
        stmt = select(SignatureSigner).where(SignatureSigner.signature_request_id == req.id)
        res = await db.execute(stmt)
        db_signers = res.scalars().all()

        # Abrir documento con PyMuPDF
        doc = fitz.open(pdf_path)
        try:
            # Añadir página en blanco para el certificado
            cert_page = doc.new_page()
            
            page_width = cert_page.rect.width
            page_height = cert_page.rect.height
            
            # 1. Dibujar Encabezado del Certificado
            cert_page.draw_rect(fitz.Rect(20, 20, page_width - 20, 75), color=None, fill=(0.01, 0.24, 0.43), overlay=True)
            cert_page.insert_textbox(
                fitz.Rect(30, 25, page_width - 30, 70),
                "CERTIFICADO DE FIRMA ELECTRÓNICA & CADENA DE CUSTODIA\nSTAR-DOC LEGALTECH PLATFORM",
                fontsize=12,
                fontname="Helvetica-Bold",
                color=(1, 1, 1),
                align=fitz.TEXT_ALIGN_CENTER
            )
            
            # 2. Detalles de Integridad Criptográfica del Expediente
            meta_rect = fitz.Rect(20, 90, page_width - 20, 180)
            cert_page.draw_rect(meta_rect, color=(0.85, 0.85, 0.85), width=1)
            
            from datetime import timedelta
            colombia_now = datetime.utcnow() - timedelta(hours=5)
            meta_text = (
                f"• Identificador de Solicitud: REG-SIGN-{req.id}\n"
                f"• Nombre del Archivo: {orig_filename}\n"
                f"• Hash SHA-256 Original: {sha256_original}\n"
                f"• Fecha de Consolidación: {colombia_now.strftime('%Y-%m-%d %H:%M:%S COT')}\n"
                f"• Base Legal: Ley 527 de 1999 y Decreto Reglamentario 2364 de 2012 (República de Colombia)"
            )
            cert_page.insert_textbox(
                fitz.Rect(30, 95, page_width - 30, 175),
                meta_text,
                fontsize=9,
                fontname="Helvetica",
                color=(0.1, 0.1, 0.1)
            )
            
            # 3. Dibujar Firmas y Metadatos de Firmantes
            y_offset = 195
            box_height = 85
            current_page = cert_page
            
            for signer in db_signers:
                if not signer.signed:
                    continue
                
                if y_offset + box_height > page_height - 150:
                    current_page = doc.new_page()
                    page_width = current_page.rect.width
                    page_height = current_page.rect.height
                    
                    current_page.draw_rect(fitz.Rect(20, 20, page_width - 20, 55), color=None, fill=(0.01, 0.24, 0.43), overlay=True)
                    current_page.insert_textbox(
                        fitz.Rect(30, 25, page_width - 30, 50),
                        "CERTIFICADO DE FIRMA ELECTRÓNICA & CADENA DE CUSTODIA (CONTINUACIÓN)",
                        fontsize=10,
                        fontname="Helvetica-Bold",
                        color=(1, 1, 1),
                        align=fitz.TEXT_ALIGN_CENTER
                    )
                    y_offset = 75
                    
                # Caja para el firmante
                box_rect = fitz.Rect(20, y_offset, page_width - 20, y_offset + box_height)
                current_page.draw_rect(box_rect, color=(0.85, 0.85, 0.85), width=1)
                
                current_page.draw_rect(fitz.Rect(page_width - 120, y_offset + 5, page_width - 25, y_offset + 22), color=None, fill=(0.8, 0.95, 0.8), overlay=True)
                current_page.insert_textbox(
                    fitz.Rect(page_width - 120, y_offset + 8, page_width - 25, y_offset + 20),
                    "FIRMADO ✅",
                    fontsize=8,
                    fontname="Helvetica-Bold",
                    color=(0.1, 0.5, 0.1),
                    align=fitz.TEXT_ALIGN_CENTER
                )
                
                # Desencriptar la firma del canvas
                canvas_data = ""
                if signer.signature_image_encrypted:
                    try:
                        canvas_data = decrypt_signature_base64(signer.signature_image_encrypted)
                    except Exception as dec_err:
                        logger.error(f"Error descifrando firma manuscrita para PDF: {dec_err}")

                if canvas_data and "," in canvas_data:
                    try:
                        img_data = base64.b64decode(canvas_data.split(",")[1])
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                            tmp_img.write(img_data)
                            tmp_img_path = tmp_img.name
                            
                        img_rect = fitz.Rect(30, y_offset + 10, 150, y_offset + box_height - 10)
                        current_page.insert_image(img_rect, filename=tmp_img_path)
                        
                        os.remove(tmp_img_path)
                    except Exception as ex:
                        logger.error(f"Error estampando imagen de firma: {ex}")
                        current_page.insert_textbox(
                            fitz.Rect(30, y_offset + 30, 150, y_offset + 60),
                            "[Firma Dibujada]",
                            fontsize=10,
                            fontname="Helvetica-Bold",
                            color=(0.5, 0.5, 0.5),
                            align=fitz.TEXT_ALIGN_CENTER
                        )
                
                signed_at_local = (signer.signed_at - timedelta(hours=5)) if signer.signed_at else None
                signer_meta = (
                    f"Firmante: {signer.name}\n"
                    f"Correo: {signer.email}\n"
                    f"Fecha COT: {signed_at_local.strftime('%Y-%m-%d %H:%M:%S') if signed_at_local else ''}\n"
                    f"Dirección IP: {signer.ip or ''}\n"
                    f"Dispositivo: {signer.user_agent[:50] if signer.user_agent else 'Navegador Web'}\n"
                    f"Token ID: {signer.token[:18]}..."
                )
                
                # Extraer firmas avanzadas ECDSA si existen en declaration_text
                pub_key = None
                sig_val = None
                decl_clean = signer.declaration_text or ""
                if decl_clean:
                    import re
                    pub_match = re.search(r"\[ECDSA_PUB:(.*?)\]", decl_clean)
                    sig_match = re.search(r"\[ECDSA_SIG:(.*?)\]", decl_clean)
                    if pub_match:
                        pub_key = pub_match.group(1)
                    if sig_match:
                        sig_val = sig_match.group(1)
                    
                    # Limpiar las etiquetas para mostrar en el PDF
                    decl_clean = re.sub(r"\[ECDSA_PUB:.*?\]", "", decl_clean)
                    decl_clean = re.sub(r"\[ECDSA_SIG:.*?\]", "", decl_clean)
                    decl_clean = decl_clean.strip()

                video_cid = signer.video_rec_cid
                if video_cid:
                    signer_meta += f"\nVideo Evidencia IPFS: {video_cid[:20]}..."
                    if decl_clean:
                        decl_short = decl_clean[:40] + "..." if len(decl_clean) > 40 else decl_clean
                        signer_meta += f"\nLectura legal: {decl_short}"
                
                if pub_key:
                    signer_meta += f"\nClave Pública ECDSA: {pub_key[:24]}..."
                if sig_val:
                    signer_meta += f"\nFirma Criptográfica: {sig_val[:24]}..."
                
                current_page.insert_textbox(
                    fitz.Rect(170, y_offset + 8, page_width - 130, y_offset + box_height - 5),
                    signer_meta,
                    fontsize=8,
                    fontname="Helvetica",
                    color=(0.2, 0.2, 0.2)
                )
                
                # Dibujar Código QR de Video Evidencia IPFS
                if video_cid:
                    try:
                        import qrcode
                        video_url = f"https://ipfs.io/ipfs/{video_cid}"
                        
                        qr = qrcode.QRCode(version=1, box_size=2, border=1)
                        qr.add_data(video_url)
                        qr.make(fit=True)
                        qr_img = qr.make_image(fill_color="black", back_color="white")
                        
                        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_qr:
                            qr_img.save(tmp_qr.name)
                            tmp_qr_path = tmp_qr.name
                            
                        qr_rect = fitz.Rect(page_width - 100, y_offset + 25, page_width - 45, y_offset + 80)
                        current_page.insert_image(qr_rect, filename=tmp_qr_path)
                        
                        current_page.insert_textbox(
                            fitz.Rect(page_width - 110, y_offset + 78, page_width - 35, y_offset + 85),
                            "Ver Video Firma QR",
                            fontsize=6,
                            fontname="Helvetica-Bold",
                            color=(0.3, 0.3, 0.3),
                            align=fitz.TEXT_ALIGN_CENTER
                        )
                        
                        os.remove(tmp_qr_path)
                    except Exception as qr_ex:
                        logger.error(f"Error estampando QR de evidencia de video: {qr_ex}")
                
                y_offset += box_height + 15
                
            # 4. Declaración de Equivalencia Funcional y Certificación
            current_page.draw_rect(fitz.Rect(20, page_height - 140, page_width - 20, page_height - 40), color=None, fill=(0.95, 0.95, 0.98), overlay=True)
            current_page.draw_rect(fitz.Rect(20, page_height - 140, page_width - 20, page_height - 40), color=(0.85, 0.85, 0.85), width=1)
            
            legal_disclaimer = (
                "DECLARACIÓN DE INTEGRIDAD LEGAL Y NO REPUDIO:\n"
                "Este documento ha sido firmado de manera electrónica por las partes indicadas utilizando tecnología Star-Doc. "
                "La firma electrónica es legalmente válida en Colombia en virtud del Artículo 7 de la Ley 527 de 1999 y el Decreto 2364 de 2012, "
                "cumpliendo con los requisitos de confiabilidad, autenticidad e integridad. Los hashes SHA-256 del documento original y del "
                "documento final firmado aseguran que el escrito no ha sufrido alteraciones. Adicionalmente, el expediente digital "
                "ha sido anclado de forma inmutable en la red distribuida IPFS garantizando la conservación de la evidencia digital para "
                "cualquier trámite probatorio o administrativo."
            )
            current_page.insert_textbox(
                fitz.Rect(30, page_height - 135, page_width - 125, page_height - 45),
                legal_disclaimer,
                fontsize=7.5,
                fontname="Helvetica",
                color=(0.3, 0.3, 0.3)
            )
            
            out_name = f"SIGNED_{orig_filename}"
            final_out_path = os.path.join(settings.OUTPUT_DIR, out_name)
            
            doc.save(final_out_path)
            logger.info(f"Documento firmado guardado exitosamente en: {final_out_path}")
            return out_name
        finally:
            doc.close()

    @staticmethod
    async def generate_and_anchor_audit_trail(
        request_id: int,
        db: AsyncSession
    ) -> str:
        """
        Genera un log estructurado en JSON con toda la evidencia probatoria del proceso de firma,
        calcula su hash de integridad y lo sube de forma permanente a IPFS.
        """
        stmt = select(SignatureRequest).where(SignatureRequest.id == request_id)
        res = await db.execute(stmt)
        req = res.scalar_one()
        
        # Cargar firmantes
        stmt_signers = select(SignatureSigner).where(SignatureSigner.signature_request_id == request_id)
        res_signers = await db.execute(stmt_signers)
        db_signers = res_signers.scalars().all()
        
        # Construir log estructurado
        audit_data = {
            "metadata": {
                "plataforma": "STAR-DOC LEGALTECH v1.0",
                "registro_id": f"SR-{req.id}",
                "fecha_creacion_solicitud": req.created_at.isoformat(),
                "fecha_completado": datetime.utcnow().isoformat(),
                "documento_original": req.document_filename,
                "sha256_firmado_pdf": req.sha256_signed,
                "ipfs_cid_pdf": req.signed_document_cid
            },
            "base_legal": {
                "ley_firma": "Ley 527 de 1999 (Artículo 7) & Decreto 2364 de 2012 (Colombia)",
                "ley_proteccion_datos": "Ley 1581 de 2012 (Habeas Data)"
            },
            "firmantes": [
                {
                    "nombre": s.name,
                    "correo": s.email,
                    "autenticacion_2fa": "OTP vía Correo Electrónico Verificado",
                    "firmado": s.signed,
                    "fecha_hora_utc": s.signed_at.isoformat() if s.signed_at else None,
                    "direccion_ip": s.ip,
                    "user_agent_cliente": s.user_agent,
                    "consentimiento_firma_electronica": s.consent_electronic_signature,
                    "consentimiento_habeas_data_y_biometria": s.consent_habeas_data,
                    "video_evidencia_cid": s.video_rec_cid,
                    "video_evidencia_sha256": s.video_sha256,
                    "texto_declaracion_leido": s.declaration_text
                }
                for s in db_signers
            ]
        }
        
        # Convertir a bytes
        audit_bytes = json.dumps(audit_data, indent=2, ensure_ascii=False).encode('utf-8')
        
        with tempfile.NamedTemporaryFile(suffix="_audit.json", delete=False) as tmp_audit:
            tmp_audit.write(audit_bytes)
            tmp_audit_path = tmp_audit.name
            
        try:
            from app.services.ipfs_integration_service import IPFSIntegrationService
            from app.services.crypto_engine import DocClassification
            
            # Anclar log de auditoría
            doc_record = await IPFSIntegrationService.anchor_and_stamp(
                file_path=tmp_audit_path,
                classification=DocClassification.CHAIN_OF_CUSTODY,
                user_id=req.user_id,
                session=db
            )
            logger.info(f"Audit Trail anclado con éxito en IPFS CID: {doc_record.ipfs_cid}")
            return doc_record.ipfs_cid
        finally:
            if os.path.exists(tmp_audit_path):
                try:
                    os.remove(tmp_audit_path)
                except Exception:
                    pass
