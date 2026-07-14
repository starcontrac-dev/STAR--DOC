import base64
import os
import logging
from email.message import EmailMessage
from fastapi import HTTPException
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import asyncio

logger = logging.getLogger(__name__)

async def send_email_with_gmail(credentials, to: str, subject: str, body: str, attachment_path: str):
    """Construye y envía un correo electrónico con un archivo adjunto usando la API de Gmail."""
    try:
        service = build('gmail', 'v1', credentials=credentials, cache_discovery=False)
        
        message = EmailMessage()
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject
        message.set_content(body)

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(attachment_path)
            message.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=file_name)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}

        def send_blocking():
            return service.users().messages().send(userId='me', body=create_message).execute()

        send_result = await asyncio.to_thread(send_blocking)
        logger.info(f"Correo enviado exitosamente a {to}. ID del mensaje: {send_result.get('id')}")
        return send_result

    except HttpError as error:
        logger.error(f"Ocurrió un error al enviar el correo: {error}")
        if error.resp.status == 401 or error.resp.status == 400: # Posible token inválido/expirado que no se pudo refrescar
             raise HTTPException(status_code=400, detail="Error de autenticación con Google. Por favor, desconecte y vuelva a conectar su cuenta en la configuración.")
        raise HTTPException(status_code=500, detail=f"Error de la API de Gmail: {error}")
    except Exception as e:
        logger.error(f"Error inesperado al enviar el correo: {e}")
        error_str = str(e)
        if "invalid_grant" in error_str or "RefreshError" in error_str:
             raise HTTPException(status_code=400, detail="La sesión de Google ha expirado. Por favor, vuelva a conectar su cuenta.")
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")
