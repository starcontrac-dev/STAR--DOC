from fastapi import APIRouter, Request, Depends, HTTPException, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import os
import uuid

from app.core.config import settings
from app.auth import get_current_active_user, get_current_user_optional
from app.services.template_manager import TemplateManager
from app.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, text
from app.models.user import User, UserRole
from app.services.stats import (
    get_total_users, get_active_users, get_document_activity, 
    get_template_usage, get_system_health,
    get_activity_history, get_hourly_activity, get_storage_distribution
)
from app.services.ai_service import ai_service

router = APIRouter(tags=["UI & Navigation"])
templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)

@router.get("/")
async def read_root(request: Request):
    """
    Renderiza la pagina de inicio (Landing Page).
    Si hay token en cookies o localstorage (client side check), el frontend decidira si redirigir.
    Aqui servimos la estructura publica.
    """
    return templates.TemplateResponse(request, "landing.html", {"hide_sidebar": True})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Renderiza la pagina de inicio de sesion (Login).
    """
    return templates.TemplateResponse(request, "login.html", {"hide_sidebar": True})

@router.get("/register-page", response_class=HTMLResponse)
async def get_register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"hide_sidebar": True})

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html", {"hide_sidebar": True})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    return templates.TemplateResponse(request, "reset_password.html", {"hide_sidebar": True, "token": token})

@router.get("/ia-chat", response_class=HTMLResponse)
async def get_ia_chat(request: Request):
    return templates.TemplateResponse(request, "ia.html", {})

@router.get("/home", response_class=HTMLResponse)
async def get_home(request: Request, template: Optional[str] = None, active_tab: str = "ia", db: AsyncSession = Depends(get_session)):
    template_files = await TemplateManager.get_all_templates_combined(db)
    variables = None
    fields = None
    detected_signers = None
    selected_template = template
    if selected_template:
        template_path = os.path.join(settings.PLANTILLAS_DIR, selected_template)
        if os.path.exists(template_path):
            variables = TemplateManager.get_template_variables(template_path=template_path)
            fields = TemplateManager.classify_template_fields(variables)
            detected_signers = TemplateManager.detect_signers_from_variables(variables)
    
    return templates.TemplateResponse(
        request,
        "index.html", 
        {
            "templates": template_files, 
            "variables": variables, 
            "fields": fields,
            "detected_signers": detected_signers,
            "selected_template": selected_template,
            "active_tab": active_tab
        }
    )

@router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/favicon.ico")

@router.get("/robots.txt", response_class=HTMLResponse)
async def get_robots_txt():
    robots_path = os.path.join(settings.STATIC_DIR, "robots.txt")
    if os.path.exists(robots_path):
        with open(robots_path, 'r') as f:
            return HTMLResponse(content=f.read(), media_type="text/plain")
    return HTMLResponse(content="", media_type="text/plain")

@router.get("/sw.js", include_in_schema=False)
async def service_worker():
    sw_path = os.path.join(settings.STATIC_DIR, "sw.js")
    if os.path.exists(sw_path):
        with open(sw_path, 'r') as f:
            content = f.read()
        return Response(
            content=content, 
            media_type="application/javascript", 
            headers={"Service-Worker-Allowed": "/"}
        )
    raise HTTPException(status_code=404, detail="Service Worker file not found")

@router.get("/offline", response_class=HTMLResponse)
async def get_offline_page(request: Request):
    return templates.TemplateResponse(request, "offline.html", {"hide_sidebar": True})


@router.get("/verificar", response_class=HTMLResponse)
async def verify_page(request: Request):
    """
    Renderiza la página pública para verificación de contratos y certificados (sin login).
    """
    return templates.TemplateResponse(request, "verify.html", {"hide_sidebar": True})


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, active_tab: str = "dashboard", db: AsyncSession = Depends(get_session)):
    # 1. Real Stats Calculation
    
    # Generated Docs (Count files in output dir)
    try:
        output_files = [f for f in os.listdir(settings.OUTPUT_DIR) if os.path.isfile(os.path.join(settings.OUTPUT_DIR, f))]
        doc_count = len(output_files)
        
        # Recent Activity (Last 5 files)
        output_files.sort(key=lambda x: os.path.getmtime(os.path.join(settings.OUTPUT_DIR, x)), reverse=True)
        recent_docs = output_files[:5]
    except Exception:
        doc_count = 0
        recent_docs = []

    # Active Templates
    try:
        templates_list = await TemplateManager.get_all_templates_combined(db)
        template_count = len(templates_list)
    except:
        template_count = 0

    # Active Users (DB Count)
    try:
        result = await db.execute(select(func.count()).select_from(User))
        user_count = result.scalar() or 1
    except Exception as e:
        print(f"Error counting users: {e}")
        user_count = 1 

    # Time Saved (Estimate: 20 mins per doc)
    time_saved_minutes = doc_count * 20
    if time_saved_minutes > 60:
        time_saved_display = f"{time_saved_minutes / 60:.1f} Horas"
    else:
        time_saved_display = f"{time_saved_minutes} Min"

    return templates.TemplateResponse(request, "dashboard.html", {
        "active_tab": active_tab,
        "stats": {
            "docs": doc_count,
            "templates": template_count,
            "users": user_count,
            "time_saved": time_saved_display
        },
        "recent_activity": recent_docs
    })

@router.get("/dashboard/data")
async def get_dashboard_data(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_session)
):
    import logging
    logger = logging.getLogger(__name__)

    # Common stats
    dashboard_data = {
        "template_usage": await get_template_usage(db),
        "document_activity": await get_document_activity(),
        "total_templates": len(await TemplateManager.get_all_templates_combined(db)),
        "activity_history": await get_activity_history(),
        "hourly_activity": await get_hourly_activity()
    }

    # Admin stats — compatible con role (SQLModel) e is_admin (BD real)
    IS_ADMIN_USER = (
        getattr(current_user, 'role', None) in ("admin", UserRole.ADMIN, UserRole.ADMIN.value) or
        getattr(current_user, 'is_admin', False) or
        current_user.username == "starcontract"
    )

    # Cargar citas autorizadas para el usuario actual
    appointments_data = []
    try:
        if IS_ADMIN_USER:
            # El administrador ve todas las citas del sistema
            query = """
                SELECT a.id, a.lead_email, a.lead_name, a.appointment_date, a.appointment_time,
                       a.duration_minutes, a.appointment_type, a.reason, a.status,
                       a.meeting_link, a.internal_notes, a.created_by, a.created_at, a.jitsi_room_name
                FROM appointments a
                ORDER BY a.appointment_date ASC, a.appointment_time ASC
            """
            params = {}
        else:
            # El usuario normal ve solo las citas creadas por él o donde su email es el invitado (lead_email)
            query = """
                SELECT a.id, a.lead_email, a.lead_name, a.appointment_date, a.appointment_time,
                       a.duration_minutes, a.appointment_type, a.reason, a.status,
                       a.meeting_link, a.internal_notes, a.created_by, a.created_at, a.jitsi_room_name
                FROM appointments a
                WHERE a.created_by = :username
                   OR (a.lead_email = :email AND a.lead_email IS NOT NULL AND a.lead_email != '')
                ORDER BY a.appointment_date ASC, a.appointment_time ASC
            """
            params = {"username": current_user.username, "email": current_user.email}
            
        rows = await db.execute(text(query), params)
        for r in rows.fetchall():
            appointments_data.append({
                "id": r[0],
                "lead_email": r[1],
                "lead_name": r[2] or "Sin nombre",
                "date": str(r[3]),
                "time": str(r[4])[:5],  # HH:MM
                "duration": r[5],
                "type": r[6],
                "reason": r[7],
                "status": r[8],
                "meeting_link": r[9],
                "notes": r[10],
                "created_by": r[11],
                "created_at": str(r[12])[:16] if r[12] else None,
                "jitsi_room_name": r[13]
            })
    except Exception as e:
        logger.warning(f"Error consultando appointments para dashboard: {e}")
        await db.rollback()

    # Inyectar estructura de citas en la respuesta general
    dashboard_data["appointments"] = {
        "total": len(appointments_data),
        "pending": len([a for a in appointments_data if a["status"] == "pending"]),
        "confirmed": len([a for a in appointments_data if a["status"] == "confirmed"]),
        "completed": len([a for a in appointments_data if a["status"] == "completed"]),
        "list": appointments_data
    }
    
    if signature_error := None:  # placeholder dummy variable si se requiriera
        pass

    if IS_ADMIN_USER:
        # Obtener contratos pendientes de aprobación (de todos los Juniors)
        from app.models.user_document import UserDocument
        stmt_pending_docs = (
            select(UserDocument, User.username)
            .join(User, UserDocument.user_id == User.id, isouter=True)
            .where(UserDocument.status == "pending_approval")
            .order_by(UserDocument.upload_date.desc())
        )
        res_pending_docs = await db.execute(stmt_pending_docs)
        pending_docs_rows = res_pending_docs.all()
        
        # Obtener plantillas pendientes de aprobación
        from app.models.template import Template
        stmt_pending_templates = select(Template).where(Template.status == "pending_approval").order_by(Template.uploaded_at.desc())
        res_pending_templates = await db.execute(stmt_pending_templates)
        pending_templates = res_pending_templates.scalars().all()

        admin_data = {
            "total_users": await get_total_users(db),
            "active_users": await get_active_users(db),
            "system_health": await get_system_health(),
            "storage_distribution": await get_storage_distribution(),
            "ai_metrics": ai_service.get_detailed_metrics(),
            "pending_documents_to_review": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "upload_date": d.upload_date.isoformat(),
                    "user_id": d.user_id,
                    "author_name": username or "Desconocido",
                    "preview": (d.content_text[:200] + "...") if d.content_text and len(d.content_text) > 200 else (d.content_text or "Sin contenido")
                } for d, username in pending_docs_rows
            ],
            "pending_templates_to_review": [
                {
                    "id": t.id,
                    "filename": t.filename,
                    "uploaded_at": t.uploaded_at.isoformat(),
                    "description": t.description
                } for t in pending_templates
            ]
        }
        dashboard_data.update(admin_data)
        dashboard_data["is_admin"] = True
    else:
        dashboard_data["is_admin"] = False
    
    return dashboard_data


@router.get("/dashboard/reunion/{room_name}", response_class=HTMLResponse)
async def serve_meeting_page(
    request: Request,
    room_name: str,
    doc: Optional[str] = None,
    token: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_session)
):
    """
    Sirve la sala de videoconferencias Jitsi Meet interactiva junto con el visualizador del PDF.
    Verifica seguridad de acceso mediante token de invitación o sesión activa.
    """
    from app.models.appointment import Appointment
    stmt = select(Appointment).where(Appointment.jitsi_room_name == room_name)
    res = await db.execute(stmt)
    appointment = res.scalars().first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="La sala de negociación virtual especificada no existe.")
        
    # Validar autorización: si no está logueado en el sistema, debe poseer el token de confirmación correcto
    if not current_user:
        if not token or token != appointment.confirmation_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado: Enlace de invitación no válido o expirado."
            )
    
    # Si no se pasó doc por Query, buscar si la cita tiene algún documento relacionado
    document_filename = doc
    if not document_filename and appointment:
        # Intentar deducir el documento asociado a partir de las notas internas
        import re
        match = re.search(r"Documento:\s*([^\s\n]+)", appointment.internal_notes or "")
        if match:
            document_filename = match.group(1).strip().rstrip(".,;\"'")
        
    # Listar todos los documentos PDFs disponibles en la carpeta output
    import glob
    output_files = []
    output_dir = settings.OUTPUT_DIR
    if os.path.exists(output_dir):
        files = glob.glob(os.path.join(output_dir, "*.pdf"))
        # Ordenar por fecha de modificación (los más recientes primero)
        files.sort(key=os.path.getmtime, reverse=True)
        output_files = [os.path.basename(f) for f in files]
        
    if not document_filename and output_files:
        document_filename = output_files[0]  # El más reciente por defecto

    # Cargar la versión firmada parcialmente si existe en lugar del original limpio
    if document_filename:
        safe_name = os.path.basename(document_filename)
        # Si ya empieza con SIGNED_, no le agregamos el prefijo
        if not safe_name.startswith("SIGNED_"):
            signed_filename = f"SIGNED_{safe_name}"
            if os.path.exists(os.path.join(output_dir, signed_filename)):
                document_filename = signed_filename
        else:
            document_filename = safe_name

    # Buscar el token del firmante actual si corresponde
    signer_token = None
    if document_filename:
        from app.models.signature import SignatureRequest, SignatureSigner
        
        safe_name = os.path.basename(document_filename)
        if safe_name.startswith("SIGNED_"):
            safe_name = safe_name.replace("SIGNED_", "", 1)
        
        stmt_sig = select(SignatureRequest).where(
            SignatureRequest.document_filename == safe_name,
            SignatureRequest.status != "completed",
            SignatureRequest.status != "expired"
        )
        res_sig = await db.execute(stmt_sig)
        sig_req = res_sig.scalars().first()
        
        if sig_req:
            db_changed = False
            existing_emails = {s.email.lower() for s in sig_req.signers if s.email}
            
            # 1. Agregar dinámicamente al abogado logueado si no está registrado
            if current_user and current_user.email.lower() not in existing_emails:
                new_signer = SignatureSigner(
                    name=current_user.username,
                    email=current_user.email.lower(),
                    signed=False,
                    signed_at=None,
                    ip=None,
                    user_agent=None,
                    token=str(uuid.uuid4()),
                    signature_request_id=sig_req.id
                )
                db.add(new_signer)
                db_changed = True
                
            # 2. Agregar dinámicamente al invitado de la cita si no está registrado
            if appointment and appointment.lead_email:
                lead_email_clean = appointment.lead_email.strip().lower()
                existing_emails = {s.email.lower() for s in sig_req.signers if s.email}
                if lead_email_clean and lead_email_clean not in existing_emails:
                    new_signer = SignatureSigner(
                        name=appointment.lead_name or lead_email_clean.split("@")[0],
                        email=lead_email_clean,
                        signed=False,
                        signed_at=None,
                        ip=None,
                        user_agent=None,
                        token=str(uuid.uuid4()),
                        signature_request_id=sig_req.id
                    )
                    db.add(new_signer)
                    db_changed = True
                    
            if db_changed:
                await db.commit()
                # Volver a cargar la sesión para que se refresque
                stmt_sig = select(SignatureRequest).where(SignatureRequest.id == sig_req.id)
                res_sig = await db.execute(stmt_sig)
                sig_req = res_sig.scalars().first()
 
            # Obtener el token del firmante actual
            if current_user:
                for s in sig_req.signers:
                    if s.email and s.email.lower() == current_user.email.lower():
                        signer_token = s.token
                        break
            elif appointment:
                for s in sig_req.signers:
                    if s.email and s.email.lower() == appointment.lead_email.lower():
                        signer_token = s.token
                        break

    # Cargar texto de la declaración legal de la cita o usar uno genérico
    declaration_text = appointment.declaration_text if appointment else "Acepto voluntariamente los términos expuestos en esta sesión legal."

    return templates.TemplateResponse(
        request, "meeting.html",
        {
            "room_name": room_name,
            "jitsi_domain": settings.JITSI_DOMAIN,
            "document_filename": document_filename,
            "output_files": output_files,
            "declaration_text": declaration_text,
            "appointment": appointment,
            "current_user": current_user,
            "signer_token": signer_token
        }
    )
