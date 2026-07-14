from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr
from typing import Optional
from app.core.config import settings
import logging
from pathlib import Path

import os
logger = logging.getLogger(__name__)

# Definir el path de forma robusta
BASE_PATH = Path(__file__).resolve().parent.parent.parent
templates_path = BASE_PATH / "templates" / "emails"

# Asegurar que existe
templates_path.mkdir(parents=True, exist_ok=True)

conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME="Star-Doc",
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=str(templates_path) # Usar string para evitar líos de WindowsPath en validación
)

async def send_email_async(subject: str, email_to: str, body: str):
    """Envía un correo electrónico de manera asíncrona."""
    try:
        message = MessageSchema(
            subject=subject,
            recipients=[email_to],
            body=body,
            subtype=MessageType.html
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Correo electrónico enviado exitosamente a {email_to}")
    except Exception as e:
        logger.error(f"Error al enviar correo electrónico a {email_to}: {e}")

class EmailService:
    @staticmethod
    async def send_appointment_confirmation(email: str, subject: str, template_body: dict):
        """
        Envía un correo de confirmación de cita utilizando plantillas Jinja2.
        """
        if "base_url" not in template_body:
            template_body["base_url"] = settings.BASE_URL
        message = MessageSchema(
            subject=subject,
            recipients=[email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="appointment_confirmation.html")
            logger.info(f"Email de confirmación enviado a {email}")
        except Exception as e:
            logger.error(f"Error enviando correo a {email}: {e}")

    @staticmethod
    async def send_lead_welcome(email: str, name: str):
        """
        Envía un correo de bienvenida al lead capturado.
        """
        template_body = {
            "name": name or "Usuario",
            "base_url": settings.BASE_URL
        }
        message = MessageSchema(
            subject="Bienvenido a Star-Doc",
            recipients=[email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="lead_welcome.html")
            logger.info(f"Email de bienvenida enviado a {email}")
        except Exception as e:
            logger.error(f"Error enviando bienvenida a {email}: {e}")

    @staticmethod
    async def send_lead_alert_to_lawyer(lawyer_email: str, lead_name: str, lead_email: str, service_interest: str, initial_message: str = None, phone: str = None):
        """Envía una notificación al abogado sobre un nuevo lead capturado."""
        template_body = {
            "name": lead_name or "Sin nombre",
            "email": lead_email,
            "phone": phone,
            "service_interest": service_interest,
            "initial_message": initial_message
        }
        message = MessageSchema(
            subject=f"Alerta: Nuevo Lead Capturado - {lead_name or lead_email}",
            recipients=[lawyer_email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="lead_notification_lawyer.html")
            logger.info(f"Email de alerta de lead enviado al abogado: {lawyer_email}")
        except Exception as e:
            logger.error(f"Error enviando alerta de lead al abogado {lawyer_email}: {e}")

    @staticmethod
    async def send_appointment_alert_to_lawyer(lawyer_email: str, appt_details: dict):
        """Envía una notificación al abogado cuando un lead agenda una cita."""
        message = MessageSchema(
            subject=f"Alerta: Nueva Cita Agendada - {appt_details.get('name')}",
            recipients=[lawyer_email],
            template_body=appt_details,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="appointment_lawyer.html")
            logger.info(f"Email de alerta de cita enviado al abogado: {lawyer_email}")
        except Exception as e:
            logger.error(f"Error enviando alerta de cita al abogado {lawyer_email}: {e}")

    @staticmethod
    async def send_document_generated_alert(recipient_email: str, document_name: str, download_url: str):
        """Envía una notificación al cliente indicando que su documento está listo."""
        template_body = {
            "document_name": document_name,
            "download_url": download_url
        }
        message = MessageSchema(
            subject=f"Su documento está listo: {document_name}",
            recipients=[recipient_email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="document_generated.html")
            logger.info(f"Email de documento listo enviado a: {recipient_email}")
        except Exception as e:
            logger.error(f"Error enviando notificación de documento listo a {recipient_email}: {e}")

    @staticmethod
    async def send_signature_request(recipient_email: str, signer_name: str, document_name: str, sign_url: str):
        """Envía una solicitud de firma electrónica a un firmante."""
        template_body = {
            "signer_name": signer_name,
            "document_name": document_name,
            "sign_url": sign_url
        }
        message = MessageSchema(
            subject=f"Solicitud de firma electrónica: {document_name}",
            recipients=[recipient_email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="signature_request.html")
            logger.info(f"Solicitud de firma electrónica enviada a: {recipient_email}")
        except Exception as e:
            logger.error(f"Error enviando solicitud de firma a {recipient_email}: {e}")

    @staticmethod
    async def send_document_signed_alert(recipient_email: str, document_name: str, signed_by: str, download_url: str, ipfs_cid: str):
        """Notifica a una parte que el proceso de firma ha sido completado."""
        template_body = {
            "document_name": document_name,
            "signed_by": signed_by,
            "download_url": download_url,
            "ipfs_cid": ipfs_cid
        }
        message = MessageSchema(
            subject=f"Proceso de firma completado: {document_name}",
            recipients=[recipient_email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="document_signed.html")
            logger.info(f"Notificación de documento firmado enviado a: {recipient_email}")
        except Exception as e:
            logger.error(f"Error enviando notificación de documento firmado a {recipient_email}: {e}")

    @staticmethod
    async def send_document_expiration_alert(lawyer_email: str, document_name: str, client_name: str, expiration_date: str, days_left: int):
        """Notifica al abogado sobre la expiración próxima de un contrato."""
        template_body = {
            "document_name": document_name,
            "client_name": client_name,
            "expiration_date": expiration_date,
            "days_left": days_left
        }
        message = MessageSchema(
            subject=f"Alerta: Expiración de contrato - {document_name} en {days_left} días",
            recipients=[lawyer_email],
            template_body=template_body,
            subtype=MessageType.html
        )
        try:
            fm = FastMail(conf)
            await fm.send_message(message, template_name="document_expiration_alert.html")
            logger.info(f"Alerta de expiración de contrato enviada a: {lawyer_email}")
        except Exception as e:
            logger.error(f"Error enviando alerta de expiración a {lawyer_email}: {e}")

    @staticmethod
    async def send_meeting_minutes_email(recipient_email: str, recipient_name: str, room_name: str, minutes_content: str, download_url: str, sha256_val: str):
        """Envía el acta de conciliación autogenerada por correo electrónico a una parte."""
        subject = f"⚖️ Acta de Conciliación Certificada - Sala: {room_name}"
        formatted_content = minutes_content.replace("\n", "<br>")
        
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
                <div style="background-color: #0b3c5d; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 20px;">ACTA DE CONCILIACIÓN CERTIFICADA</h1>
                    <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">Star-Doc LegalTech Platform</p>
                </div>
                <div style="background-color: white; padding: 30px; border: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                    <p>Estimado/a <strong>{recipient_name}</strong>,</p>
                    <p>Le notificamos que el Acta de Conciliación correspondiente a la reunión en la sala virtual <strong>{room_name}</strong> ha sido redactada de forma íntegra por Inteligencia Artificial y certificada criptográficamente en nuestro sistema.</p>
                    
                    <div style="background-color: #f1f5f9; padding: 15px; border-left: 4px solid #0b3c5d; margin: 20px 0; border-radius: 4px;">
                        <h3 style="margin: 0 0 10px 0; font-size: 14px; color: #0b3c5d;">Datos de Integridad Criptográfica:</h3>
                        <p style="margin: 5px 0; font-size: 12px; font-family: monospace;"><strong>Hash SHA-256 de Origen:</strong> {sha256_val}</p>
                        <p style="margin: 5px 0; font-size: 12px;"><strong>Estado:</strong> Certificado e Inalterable</p>
                    </div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{download_url}" style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; display: inline-block;">📥 Descargar Acta Certificada (.md)</a>
                    </div>

                    <h3 style="border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; margin-top: 30px; color: #0b3c5d;">Contenido del Acta:</h3>
                    <div style="background-color: #fafafa; border: 1px solid #f1f5f9; padding: 20px; border-radius: 6px; font-size: 13px; max-height: 400px; overflow-y: auto; font-family: 'Courier New', Courier, monospace;">
                        {formatted_content}
                    </div>

                    <p style="margin-top: 30px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 20px;">
                        Esta es una notificación formal de Star-Doc. El hash y contenido del acta constituyen prueba de equivalencia funcional y no repudio de acuerdo con la Ley 527 de 1999 de Colombia.
                    </p>
                </div>
            </body>
        </html>
        """
        await send_email_async(subject, recipient_email, body)

    @staticmethod
    async def send_document_signed_email_custom(recipient_email: str, recipient_name: str, document_name: str, download_url: str, sha256_val: str, ipfs_cid: str):
        """Notifica por correo a un firmante que el proceso de firmado ha finalizado con éxito, proveyendo detalles criptográficos de no repudio."""
        subject = f"📝 Documento Firmado Exitosamente - {document_name}"
        ipfs_text = f'<p style="margin: 5px 0; font-size: 12px; font-family: monospace;"><strong>Dirección IPFS (CID):</strong> <a href="https://ipfs.io/ipfs/{ipfs_cid}">{ipfs_cid}</a></p>' if (ipfs_cid and ipfs_cid != "local") else '<p style="margin: 5px 0; font-size: 12px;"><strong>Almacenamiento:</strong> Servidor Local Seguro (IPFS Deshabilitado)</p>'

        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
                <div style="background-color: #1e3a8a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 20px;">PROCESO DE FIRMA COMPLETADO</h1>
                    <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">Star-Doc LegalTech Platform</p>
                </div>
                <div style="background-color: white; padding: 30px; border: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                    <p>Estimado/a <strong>{recipient_name}</strong>,</p>
                    <p>Le informamos que el proceso de firma electrónica para el documento <strong>{document_name}</strong> ha finalizado con éxito. Todos los participantes han firmado el acuerdo de forma válida.</p>
                    
                    <div style="background-color: #f1f5f9; padding: 15px; border-left: 4px solid #1e3a8a; margin: 20px 0; border-radius: 4px;">
                        <h3 style="margin: 0 0 10px 0; font-size: 14px; color: #1e3a8a;">Datos de Integridad y Firma:</h3>
                        <p style="margin: 5px 0; font-size: 12px; font-family: monospace;"><strong>Hash SHA-256 Firmado:</strong> {sha256_val}</p>
                        {ipfs_text}
                        <p style="margin: 5px 0; font-size: 12px;"><strong>Garantía:</strong> Equivalencia Funcional y No Repudio (Ley 527 de 1999)</p>
                    </div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{download_url}" style="background-color: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; display: inline-block;">📥 Descargar Documento Firmado (PDF)</a>
                    </div>

                    <p style="margin-top: 30px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 20px;">
                        Este documento electrónico cuenta con firma electrónica e integridad criptográfica. Star-Doc actúa como tercero de confianza registrado.
                    </p>
                </div>
            </body>
        </html>
        """
        await send_email_async(subject, recipient_email, body)

    @staticmethod
    async def send_collaborative_invitation(
        recipient_email: str,
        document_name: str,
        colab_url: str,
        sender_name: str,
        custom_message: Optional[str] = None
    ):
        """Envía un correo invitando a co-editar un documento en CryptPad.fr."""
        subject = f"⚡ Invitación a co-edición en tiempo real: {document_name}"
        message_html = f"<p>Mensaje personalizado de {sender_name}:</p><blockquote style='border-left: 3px solid #06b6d4; padding-left: 10px; font-style: italic; color: #475569;'>\"{custom_message}\"</blockquote>" if custom_message else ""
        
        body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8fafc;">
                <div style="background-color: #06b6d4; color: black; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 18px; color: #0f172a;">INVITACIÓN A CO-EDICIÓN EN LA NUBE</h1>
                    <p style="margin: 5px 0 0 0; font-size: 12px; opacity: 0.9; color: #0f172a;">Star-Doc LegalTech Platform</p>
                </div>
                <div style="background-color: white; padding: 30px; border: 1px solid #e2e8f0; border-radius: 0 0 8px 8px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                    <p>Estimado/a colega,</p>
                    <p>El abogado <strong>{sender_name}</strong> le ha invitado a unirse a la co-edición en tiempo real del documento <strong>{document_name}</strong> en la plataforma Star-Doc.</p>
                    
                    {message_html}

                    <div style="background-color: #ecfeff; padding: 15px; border-left: 4px solid #06b6d4; margin: 20px 0; border-radius: 4px;">
                        <h3 style="margin: 0 0 10px 0; font-size: 13px; color: #0891b2;">Información del Entorno Cooperativo:</h3>
                        <p style="margin: 5px 0; font-size: 12px; color: #334155;">• <strong>Herramienta:</strong> CryptPad.fr (Zero-Knowledge, Cifrado en Cliente)</p>
                        <p style="margin: 5px 0; font-size: 12px; color: #334155;">• <strong>Privacidad:</strong> Los servidores no registran los textos en claro por su encriptación criptográfica.</p>
                    </div>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{colab_url}" target="_blank" style="background-color: #0891b2; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px; display: inline-block; box-shadow: 0 4px 10px rgba(8,145,178,0.3);">🚀 Unirse a la Edición en Tiempo Real</a>
                    </div>

                    <p style="margin-top: 30px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 20px;">
                        Esta es una notificación automática de Star-Doc. Al finalizar la co-edición en la suite, la versión final se consolidará en un PDF bajo firma y sellado de tiempo de acuerdo con la Ley 527 de 1999 de Colombia.
                    </p>
                </div>
            </body>
        </html>
        """
        await send_email_async(subject, recipient_email, body)

