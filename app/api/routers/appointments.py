import logging
import asyncio
from datetime import date, time, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, EmailStr
from jose import jwt

from app.database import get_session
from app.auth import get_current_user_optional, get_current_active_user, SECRET_KEY, ALGORITHM
from app.models.user import User
from app.models.lead import Lead, LeadStatus, LeadSource
from app.models.appointment import Appointment, AppointmentStatus, AppointmentType
from app.services.google_calendar_service import GoogleCalendarService
from app.services.email import EmailService
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])

class AppointmentCreate(BaseModel):
    client_name: str
    client_phone: str
    client_email: EmailStr
    appointment_date: date
    appointment_time: time
    reason: str
    appointment_type: Optional[str] = "video_call"

class AppointmentResponse(BaseModel):
    id: int
    lead_id: Optional[int]
    lead_name: Optional[str]
    lead_email: str
    appointment_date: date
    appointment_time: time
    meeting_link: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

@router.post("/schedule", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def schedule_appointment(
    data: AppointmentCreate,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session)
):
    """
    Agenda una cita de asesoría legal en Star-Doc.
    Soporta agendamiento autenticado y anónimo (leads de landing/widget).
    Sincroniza con Google Calendar y genera enlace de Google Meet.
    Envía notificaciones por correo de confirmación al cliente y alerta al administrador/abogados.
    """
    # Usar siempre los datos provistos en el formulario para evitar sobrescribir con la cuenta del administrador autenticado
    client_email = data.client_email.lower()
    client_name = data.client_name

    # 1. Validar restricciones de tiempo profesional (Colombia - America/Bogota)
    import pytz
    COLOMBIA_TZ = pytz.timezone("America/Bogota")
    
    # Combinar fecha y hora
    naive_dt = datetime.combine(data.appointment_date, data.appointment_time)
    appointment_dt = COLOMBIA_TZ.localize(naive_dt)
    
    # Fecha y hora actual en Colombia
    now_colombia = datetime.now(COLOMBIA_TZ)
    
    # 1.1. Validar que no sea en el pasado y tenga al menos 2 horas de anticipación
    if appointment_dt < now_colombia + timedelta(hours=2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las citas deben programarse con un mínimo de 2 horas de anticipación y no pueden ser en el pasado."
        )
        
    # 1.2. Validar días laborales (Lunes = 0, Domingo = 6)
    if appointment_dt.weekday() >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las asesorías legales solo están disponibles en días laborales (de lunes a viernes)."
        )
        
    # 1.3. Validar horario de oficina (de 08:00 a 18:00)
    work_start = time(8, 0)
    work_end = time(18, 0)
    # Las citas duran 30 minutos en el principal
    appointment_end_time = (appointment_dt + timedelta(minutes=30)).time()
    if data.appointment_time < work_start or appointment_end_time > work_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las citas solo se realizan en horario de oficina de 08:00 a 18:00 (hora de Colombia)."
        )

    # 2. Comprobar colisiones locales en la base de datos de Star-Doc (Evitar Double Booking)
    start_datetime = datetime.combine(data.appointment_date, data.appointment_time)
    end_datetime = start_datetime + timedelta(minutes=30)
    
    statement_appt = select(Appointment).where(
        Appointment.appointment_date == data.appointment_date,
        Appointment.status == AppointmentStatus.CONFIRMED.value
    )
    result_appt = await session.execute(statement_appt)
    existing_appts = result_appt.scalars().all()
    
    for appt in existing_appts:
        appt_start = datetime.combine(appt.appointment_date, appt.appointment_time)
        appt_end = appt_start + timedelta(minutes=appt.duration_minutes)
        # Si se solapan los intervalos
        if not (end_datetime <= appt_start or start_datetime >= appt_end):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe una cita programada en ese rango horario ({appt.appointment_time.strftime('%H:%M')} - {appt_end.strftime('%H:%M')}). Por favor, selecciona otro horario."
            )

    # 3. Sincronizar con Google Calendar
    meet_link = None
    try:
        dt_str = f"{data.appointment_date}T{data.appointment_time}:00"
        summary = f"Asesoría Legal Star-Doc: {client_name}"
        description = f"Motivo: {data.reason}\nTeléfono: {data.client_phone}\nAgendado vía Widget de Landing Page."
        
        google_result = await GoogleCalendarService.create_event(
            summary=summary,
            description=description,
            start_iso=dt_str,
            attendee_email=client_email,
            duration_minutes=30
        )
        
        if google_result.get("success"):
            meet_link = google_result.get("meet_link")
            logger.info("Cita programada con éxito en Google Calendar.")
        else:
            logger.warning(f"No se pudo sincronizar en Google Calendar: {google_result.get('error')}. Se procede a guardar localmente.")
    except Exception as e:
        logger.error(f"Error al sincronizar con Google Calendar: {e}. Se guarda cita local.")

    # 4. Obtener o crear Lead para asociar a la cita
    lead_result = await session.execute(select(Lead).where(Lead.email == client_email))
    lead = lead_result.scalars().first()
    
    if not lead:
        lead = Lead(
            email=client_email,
            name=client_name,
            phone=data.client_phone,
            status=LeadStatus.APPOINTED.value,
            source=LeadSource.CHAT_WIDGET.value,
            service_interest=data.reason
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
    else:
        lead.status = LeadStatus.APPOINTED.value
        if not lead.name:
            lead.name = client_name
        if data.client_phone:
            lead.phone = data.client_phone
        session.add(lead)
        await session.commit()

    # 5. Guardar la Cita en Base de Datos local
    final_meeting_link = meet_link

    appointment = Appointment(
        lead_id=lead.id,
        lead_email=client_email,
        lead_name=client_name,
        appointment_date=data.appointment_date,
        appointment_time=data.appointment_time,
        appointment_type=data.appointment_type or AppointmentType.VIDEO_CALL.value,
        reason=data.reason,
        meeting_link=final_meeting_link,
        jitsi_room_name=None,
        declaration_text=f"Yo, {client_name}, acepto voluntariamente los términos de la reunión y la resolución legal de esta sesión.",
        status=AppointmentStatus.CONFIRMED.value # Autoconfirmado al ser agendado por el usuario
    )
    appointment.generate_token()
    
    session.add(appointment)
    await session.commit()
    await session.refresh(appointment)

    # 6. Notificaciones de Correo
    # 6.1. Correo al cliente
    try:
        confirm_data = {
            "name": client_name,
            "date": data.appointment_date.strftime("%d/%m/%Y"),
            "time": data.appointment_time.strftime("%H:%M"),
            "type": appointment.appointment_type,
            "reason": data.reason,
            "meeting_link": meet_link,
            "token": appointment.confirmation_token
        }
        asyncio.create_task(
            EmailService.send_appointment_confirmation(
                email=client_email,
                subject=f"Confirmación de tu Asesoría Legal Star-Doc - {data.appointment_date.strftime('%d/%m/%Y')}",
                template_body=confirm_data
            )
        )
    except Exception as e:
        logger.error(f"Error al enviar correo de confirmación de cita: {e}")

    # 6.2. Alerta a la administración y abogados (Enviado a starcontrac@gmail.com y abogados del sistema)
    try:
        # Construimos set de destinatarios para evitar duplicados
        recipients = {"starcontrac@gmail.com"}
        
        # Consultar administradores en BD
        lawyers_result = await session.execute(select(User).where(User.role == "admin"))
        lawyers = lawyers_result.scalars().all()
        for lawyer in lawyers:
            if lawyer.email:
                recipients.add(lawyer.email.lower().strip())
                
        # Si por algún motivo no hay ningún correo, añadimos el mail de configuración
        if not recipients:
            recipients.add(settings.MAIL_FROM)
            
        for r_email in recipients:
            asyncio.create_task(
                EmailService.send_appointment_alert_to_lawyer(
                    lawyer_email=r_email,
                    appt_details={
                        "name": client_name,
                        "email": client_email,
                        "phone": data.client_phone,
                        "date": data.appointment_date.strftime("%d/%m/%Y"),
                        "time": data.appointment_time.strftime("%H:%M"),
                        "type": appointment.appointment_type,
                        "reason": data.reason,
                        "meeting_link": meet_link
                    }
                )
            )
    except Exception as e:
        logger.error(f"Error al enviar alerta de cita a los abogados/administración: {e}")

    return appointment


# --- Nuevos Modelos de Validación ---
class AppointmentStatusUpdate(BaseModel):
    status: str
    cancellation_reason: Optional[str] = None

class AppointmentReschedule(BaseModel):
    appointment_date: date
    appointment_time: time


# --- Endpoints de Edición ---

@router.patch("/{appt_id}/status", response_model=AppointmentResponse)
async def update_appointment_status(
    appt_id: int,
    payload: AppointmentStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Actualiza el estado de una cita.
    Permite cancelar o marcar como completada una cita de asesoría.
    Si se cancela, se registra la fecha y se envía un correo de notificación.
    """
    appointment = await session.get(Appointment, appt_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La cita especificada no existe."
        )

    # Verificar si es admin o es el creador de la cita
    is_role_admin = getattr(current_user, 'role', None) == "admin" or getattr(current_user, 'is_admin', False)
    is_username_admin = current_user.username == "starcontract"
    is_creator = appointment.created_by == current_user.username

    if not (is_role_admin or is_username_admin or is_creator):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: solo el administrador o el creador de la reunión pueden cambiar su estado."
        )

    # Validar el estado
    status_lower = payload.status.lower()
    valid_statuses = [s.value for s in AppointmentStatus]
    if status_lower not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado '{payload.status}' no válido. Valores permitidos: {', '.join(valid_statuses)}"
        )

    # Actualizar estado
    appointment.status = status_lower
    appointment.updated_at = datetime.utcnow()

    # Lógica específica para cancelación
    if status_lower == AppointmentStatus.CANCELLED.value:
        appointment.cancelled_at = datetime.utcnow()
        appointment.cancellation_reason = payload.cancellation_reason
        
        # Enviar correo de notificación de cancelación al cliente de manera asíncrona
        try:
            from app.services.email import send_email_async
            subject = f"Cancelación de tu Asesoría Legal Star-Doc - {appointment.appointment_date.strftime('%d/%m/%Y')}"
            body = (
                f"<div style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;'>"
                f"<h2 style='color: #ef4444; margin-bottom: 20px;'>Tu Cita ha sido Cancelada</h2>"
                f"<p>Hola <strong>{appointment.lead_name}</strong>,</p>"
                f"<p>Te informamos que tu cita de asesoría legal programada para el día <strong>{appointment.appointment_date.strftime('%d/%m/%Y')}</strong> a las <strong>{appointment.appointment_time.strftime('%H:%M')}</strong> ha sido cancelada por el administrador.</p>"
                f"<p>Si crees que esto es un error o deseas agendar una nueva asesoría, por favor visita nuestro portal.</p>"
                f"<hr style='border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;' />"
                f"<p style='font-size: 11px; color: #94a3b8;'>Star-Doc - Plataforma de Inteligencia Documental Constitucional</p>"
                f"</div>"
            )
            asyncio.create_task(send_email_async(subject, appointment.lead_email, body))
        except Exception as e:
            logger.error(f"Error al enviar correo de cancelación: {e}")

    session.add(appointment)
    await session.commit()
    await session.refresh(appointment)
    return appointment


@router.patch("/{appt_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appt_id: int,
    payload: AppointmentReschedule,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Reprograma la fecha y hora de una cita de asesoría.
    Valida colisiones, genera un nuevo enlace en Google Calendar y envía correo de notificación.
    """
    # Verificar si es admin
    is_role_admin = getattr(current_user, 'role', None) == "admin" or getattr(current_user, 'is_admin', False)
    is_username_admin = current_user.username == "starcontract"
    if not (is_role_admin or is_username_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: solo administradores pueden gestionar citas."
        )

    appointment = await session.get(Appointment, appt_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La cita especificada no existe."
        )

    # 1. Validar restricciones de tiempo profesional (Colombia)
    import pytz
    COLOMBIA_TZ = pytz.timezone("America/Bogota")
    
    naive_dt = datetime.combine(payload.appointment_date, payload.appointment_time)
    appointment_dt = COLOMBIA_TZ.localize(naive_dt)
    
    now_colombia = datetime.now(COLOMBIA_TZ)
    
    if appointment_dt < now_colombia + timedelta(hours=2):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las citas deben reprogramarse con un mínimo de 2 horas de anticipación y no pueden ser en el pasado."
        )
        
    if appointment_dt.weekday() >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las asesorías legales solo están disponibles en días laborales (de lunes a viernes)."
        )
        
    work_start = time(8, 0)
    work_end = time(18, 0)
    appointment_end_time = (appointment_dt + timedelta(minutes=30)).time()
    if payload.appointment_time < work_start or appointment_end_time > work_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las citas solo se realizan en horario de oficina de 08:00 a 18:00 (hora de Colombia)."
        )

    # 2. Comprobar colisiones locales en la base de datos de Star-Doc (excluyendo esta misma cita)
    start_datetime = datetime.combine(payload.appointment_date, payload.appointment_time)
    end_datetime = start_datetime + timedelta(minutes=30)
    
    statement_appt = select(Appointment).where(
        Appointment.appointment_date == payload.appointment_date,
        Appointment.status == AppointmentStatus.CONFIRMED.value,
        Appointment.id != appt_id
    )
    result_appt = await session.execute(statement_appt)
    existing_appts = result_appt.scalars().all()
    
    for appt in existing_appts:
        appt_start = datetime.combine(appt.appointment_date, appt.appointment_time)
        appt_end = appt_start + timedelta(minutes=appt.duration_minutes)
        if not (end_datetime <= appt_start or start_datetime >= appt_end):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya existe otra cita programada en ese rango horario ({appt.appointment_time.strftime('%H:%M')} - {appt_end.strftime('%H:%M')}). Por favor, selecciona otro horario."
            )

    # 3. Sincronizar nuevo evento con Google Calendar
    meet_link = None
    try:
        dt_str = f"{payload.appointment_date}T{payload.appointment_time}:00"
        summary = f"Asesoría Legal Star-Doc: {appointment.lead_name} (REPROGRAMADA)"
        description = f"Motivo: {appointment.reason}\nTeléfono (Lead): {appointment.lead_email}\nCita reprogramada por el administrador."
        
        google_result = await GoogleCalendarService.create_event(
            summary=summary,
            description=description,
            start_iso=dt_str,
            attendee_email=appointment.lead_email,
            duration_minutes=30
        )
        
        if google_result.get("success"):
            meet_link = google_result.get("meet_link")
            logger.info("Cita reprogramada con éxito en Google Calendar.")
    except Exception as e:
        logger.error(f"Error al reprogramar en Google Calendar: {e}")

    # 4. Actualizar base de datos
    appointment.appointment_date = payload.appointment_date
    appointment.appointment_time = payload.appointment_time
    if meet_link:
        appointment.meeting_link = meet_link
    appointment.status = AppointmentStatus.RESCHEDULED.value
    appointment.updated_at = datetime.utcnow()

    # 5. Enviar correo de notificación de reprogramación
    try:
        from app.services.email import send_email_async
        subject = f"Reprogramación de tu Asesoría Legal Star-Doc - {payload.appointment_date.strftime('%d/%m/%Y')}"
        meet_section = ""
        if appointment.meeting_link:
            meet_section = (
                f"<p style='margin: 15px 0; text-align: center;'>"
                f"<a href='{appointment.meeting_link}' style='background-color: #4f46e5; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; box-shadow: 0 4px 6px rgba(79, 70, 229, 0.15);'>Entrar a Google Meet</a>"
                f"</p>"
                f"<p style='font-size: 12px; color: #64748b;'>Enlace de la videollamada: <a href='{appointment.meeting_link}'>{appointment.meeting_link}</a></p>"
            )
        body = (
            f"<div style='font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;'>"
            f"<h2 style='color: #4f46e5; margin-bottom: 20px;'>Tu Cita ha sido Reprogramada</h2>"
            f"<p>Hola <strong>{appointment.lead_name}</strong>,</p>"
            f"<p>Te informamos que tu cita de asesoría legal ha sido reprogramada por el administrador.</p>"
            f"<div style='background-color: #f8fafc; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #4f46e5;'>"
            f"<p style='margin: 5px 0;'><strong>Nueva Fecha:</strong> {payload.appointment_date.strftime('%d/%m/%Y')}</p>"
            f"<p style='margin: 5px 0;'><strong>Nueva Hora:</strong> {payload.appointment_time.strftime('%H:%M')} (Hora de Colombia)</p>"
            f"<p style='margin: 5px 0;'><strong>Motivo:</strong> {appointment.reason}</p>"
            f"</div>"
            f"{meet_section}"
            f"<hr style='border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;' />"
            f"<p style='font-size: 11px; color: #94a3b8;'>Star-Doc - Plataforma de Inteligencia Documental Constitucional</p>"
            f"</div>"
        )
        asyncio.create_task(send_email_async(subject, appointment.lead_email, body))
    except Exception as e:
        logger.error(f"Error al enviar correo de reprogramación: {e}")

    session.add(appointment)
    await session.commit()
    await session.refresh(appointment)
    return appointment

