"""
Router de API para solicitudes y ejecución de firmas electrónicas en STAR-DOC.
"""
import logging
import secrets
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth import get_current_active_user
from app.database import get_session
from app.models.user import User
from app.models.signature import SignatureRequest, SignatureSigner
from app.services.signature_service import SignatureService
from app.services.email import EmailService, send_email_async
from app.core.config import settings
from app.core.utils import get_base_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Electronic Signature"])
templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)

# --- Esquemas de Validación Pydantic ---
class SignerInput(BaseModel):
    name: str
    email: EmailStr

class SignatureRequestCreate(BaseModel):
    document_filename: str
    signers: List[SignerInput]
    expiration_days: Optional[int] = 7
    classification: Optional[str] = "chain_of_custody"

class SignPayload(BaseModel):
    signature_base64: str
    consent_electronic_signature: bool
    consent_habeas_data: bool
    public_key: Optional[str] = None
    crypto_signature: Optional[str] = None

class OTPVerifyPayload(BaseModel):
    otp: str


# --- Endpoints ---

@router.post("/signatures/request")
async def create_signature_request(
    payload: SignatureRequestCreate,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Crea una nueva solicitud de firma electrónica y despacha los correos a los firmantes.
    Valida previamente que el documento esté aprobado por un revisor Senior.
    """
    try:
        # Validar el workflow de aprobación del documento
        from app.models.user_document import UserDocument
        stmt = select(UserDocument).where(UserDocument.filename == payload.document_filename)
        res = await db.execute(stmt)
        user_doc = res.scalar_one_or_none()
        
        if user_doc:
            if user_doc.status != "approved":
                raise HTTPException(
                    status_code=400,
                    detail=f"No es posible iniciar el proceso de firma. El documento '{payload.document_filename}' no ha sido aprobado formalmente por un revisor Senior (Estado actual: '{user_doc.status}')."
                )
            # Avanzar el estado a pending_signatures en el workflow
            user_doc.status = "pending_signatures"
            db.add(user_doc)
            await db.commit()

        signers_list = [{"name": s.name, "email": s.email} for s in payload.signers]
        base_url = get_base_url(request)
        
        req = await SignatureService.create_signature_request(
            user_id=current_user.id,
            document_filename=payload.document_filename,
            signers_list=signers_list,
            expiration_days=payload.expiration_days,
            classification=payload.classification or "chain_of_custody",
            base_url=base_url,
            db=db
        )
        
        return {
            "success": True,
            "request_id": req.id,
            "document_filename": req.document_filename,
            "expiration": req.expiration.isoformat(),
            "signers": [
                {"name": s.name, "email": s.email, "signed": s.signed}
                for s in req.signers
            ]
        }
    except HTTPException as he:
        raise he
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        logger.error(f"Error creando solicitud de firma: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno al crear solicitud: {str(e)}")


@router.get("/signatures/{request_id}")
async def get_signature_request(
    request_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    """
    Obtiene los detalles y el estado actual de una solicitud de firma.
    """
    req = await db.get(SignatureRequest, request_id)
    if not req or (req.user_id != current_user.id and current_user.role != "admin"):
        raise HTTPException(status_code=404, detail="Solicitud de firma no encontrada.")
        
    return {
        "id": req.id,
        "document_filename": req.document_filename,
        "status": req.status,
        "created_at": req.created_at.isoformat(),
        "expiration": req.expiration.isoformat(),
        "signed_document_cid": req.signed_document_cid,
        "sha256_signed": req.sha256_signed,
        "signers": [
            {
                "name": s.name,
                "email": s.email,
                "signed": s.signed,
                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                "ip": s.ip
            }
            for s in req.signers
        ]
    }


# --- Endpoints Públicos de Firma (Sin Autenticación, controlados por OTP) ---

@router.get("/sign/{token}", response_class=HTMLResponse)
async def serve_sign_page(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_session)
):
    """
    Sirve la interfaz gráfica de firma o solicita autenticación OTP en función de la cookie de sesión.
    """
    found = await SignatureService.get_signature_request_by_token(token, db)
    if not found:
        return HTMLResponse(
            content=f"""
            <html>
            <body style="font-family: sans-serif; background-color: #050505; color: #e2e8f0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0;">
                <div style="background-color: #0c101f; padding: 40px; border-radius: 12px; border: 1px solid #1e293b; text-align: center; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
                    <h1 style="color: #ef4444; font-size: 24px; margin-bottom: 15px;">Firma No Disponible</h1>
                    <p style="color: #94a3b8; font-size: 14px; line-height: 1.6;">El enlace de firma es inválido, ha expirado o ya no está activo en el sistema Star-Doc.</p>
                    <a href="https://starcontract.free.nf" style="display: inline-block; margin-top: 20px; background-color: #4f46e5; color: white; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; font-size: 14px;">Ir a Star-Doc</a>
                </div>
            </body>
            </html>
            """,
            status_code=404
        )
        
    req: SignatureRequest = found["request"]
    signer: SignatureSigner = found["signer"]
    
    # 1. Verificar si la sesión ya fue validada con OTP vía cookies
    otp_cookie = request.cookies.get(f"otp_verified_{token}")
    if otp_cookie != "verified":
        # Renderizar la página de verificación OTP (2FA)
        return templates.TemplateResponse(
            request, "sign_otp.html",
            {
                "token": token,
                "signer_name": signer.name,
                "signer_email": signer.email,
                "document_filename": req.document_filename
            }
        )
    
    # 2. Si la cookie es válida, sirve la pantalla de firma
    import os
    filename_to_show = req.document_filename
    signed_filename = f"SIGNED_{req.document_filename}"
    if os.path.exists(os.path.join(settings.OUTPUT_DIR, signed_filename)):
        filename_to_show = signed_filename
        
    return templates.TemplateResponse(
        request, "sign.html",
        {
            "token": token,
            "document_filename": filename_to_show,
            "signer_name": signer.name,
            "signer_email": signer.email,
            "expiration": req.expiration.strftime("%Y-%m-%d"),
            "signed": signer.signed
        }
    )


@router.post("/sign/{token}/request-otp")
async def request_otp_challenge(
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session)
):
    """
    Genera un código OTP de 6 dígitos con vigencia de 10 minutos y lo envía al firmante.
    """
    stmt = select(SignatureSigner).where(SignatureSigner.token == token)
    res = await db.execute(stmt)
    signer = res.scalar_one_or_none()
    
    if not signer:
        raise HTTPException(status_code=404, detail="Enlace de firma inválido o expirado.")
        
    if signer.signed:
        raise HTTPException(status_code=400, detail="Este firmante ya ha firmado el documento.")
        
    # Generar OTP de 6 dígitos numéricos
    otp_code = "".join(secrets.choice("0123456789") for _ in range(6))
    
    # Guardar en base de datos
    signer.otp_code = otp_code
    signer.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    db.add(signer)
    await db.commit()
    
    # Despachar correo en segundo plano
    background_tasks.add_task(
        send_email_async,
        subject="Código de Seguridad - Firma Electrónica Star-Doc",
        email_to=signer.email,
        body=f"""
        <div style="font-family: sans-serif; max-width: 500px; margin: 0 auto; padding: 25px; border: 1px solid #e2e8f0; border-radius: 16px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <h2 style="color: #4f46e5; font-size: 20px; font-weight: bold; margin-bottom: 8px; text-align: center;">Autenticación de Doble Factor</h2>
            <p style="color: #64748b; font-size: 13px; text-align: center; margin-bottom: 25px;">Para acceder y firmar el documento en la plataforma Star-Doc, ingrese el siguiente código de seguridad:</p>
            
            <div style="font-size: 32px; font-weight: 800; background-color: #f1f5f9; padding: 18px; text-align: center; border-radius: 12px; letter-spacing: 6px; color: #1e3a8a; font-family: monospace; margin: 20px 0;">
                {otp_code}
            </div>
            
            <p style="color: #94a3b8; font-size: 11px; text-align: center; margin-top: 25px;">Este código es de un solo uso y vencerá en 10 minutos por razones de seguridad.</p>
            <div style="border-top: 1px solid #f1f5f9; margin-top: 25px; padding-top: 15px; text-align: center;">
                <small style="color: #cbd5e1; font-size: 10px; font-weight: 600; text-transform: uppercase; tracking: 1px;">Star-Doc - Ley 527 de 1999</small>
            </div>
        </div>
        """
    )
    
    return {"success": True, "message": "Código de seguridad OTP enviado."}


@router.post("/sign/{token}/verify-otp")
async def verify_otp_challenge(
    token: str,
    payload: OTPVerifyPayload,
    response: Response,
    db: AsyncSession = Depends(get_session)
):
    """
    Verifica el OTP enviado por el usuario. Si coincide y está vigente, otorga la cookie de autenticación temporal.
    """
    stmt = select(SignatureSigner).where(SignatureSigner.token == token)
    res = await db.execute(stmt)
    signer = res.scalar_one_or_none()
    
    if not signer:
        raise HTTPException(status_code=404, detail="Enlace inválido.")
        
    if not signer.otp_code or not signer.otp_expires_at or signer.otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="El código de seguridad ha expirado o no ha sido generado. Solicite uno nuevo.")
        
    if signer.otp_code != payload.otp.strip():
        raise HTTPException(status_code=400, detail="Código de seguridad incorrecto.")
        
    # Limpiar OTP usado
    signer.otp_code = None
    signer.otp_expires_at = None
    db.add(signer)
    await db.commit()
    
    # Crear cookie HTTPOnly segura por 1 hora
    response.set_cookie(
        key=f"otp_verified_{token}",
        value="verified",
        max_age=3600,
        httponly=True,
        samesite="lax",
        secure=False # Cambiar a True en producción si se utiliza SSL/HTTPS
    )
    
    return {"success": True, "message": "Autenticación OTP exitosa."}


@router.post("/sign/{token}")
async def submit_signature(
    request: Request,
    token: str,
    payload: SignPayload,
    db: AsyncSession = Depends(get_session)
):
    """
    Procesa el envío de la firma del canvas del usuario firmante. Requiere cookie OTP válida.
    """
    # 1. Validar cookie de sesión OTP
    otp_cookie = request.cookies.get(f"otp_verified_{token}")
    if otp_cookie != "verified":
        raise HTTPException(status_code=401, detail="Sesión de seguridad no verificada (OTP requerido).")
        
    # 2. Validar consentimientos obligatorios
    if not payload.consent_electronic_signature or not payload.consent_habeas_data:
        raise HTTPException(status_code=400, detail="Debe aceptar expresamente las políticas de firma electrónica y protección de datos.")

    client_ip = request.client.host if request.client else "127.0.0.1"
    real_ip = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For") or client_ip
    user_agent = request.headers.get("User-Agent", "Desconocido")
    
    try:
        base_url = get_base_url(request)
        res = await SignatureService.process_signature(
            token=token,
            canvas_base64=payload.signature_base64,
            client_ip=real_ip,
            user_agent=user_agent,
            consent_electronic_signature=payload.consent_electronic_signature,
            consent_habeas_data=payload.consent_habeas_data,
            base_url=base_url,
            db=db,
            public_key=payload.public_key,
            crypto_signature=payload.crypto_signature
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error procesando firma electrónica: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
