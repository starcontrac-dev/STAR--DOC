"""
Servicio para la ejecución de herramientas del Secretario IA.
Maneja la lógica de BD y validaciones para capture_lead, check_availability, etc.
"""
import re
from datetime import date, time, datetime, timedelta
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.models.lead import Lead, LeadStatus
from app.models.appointment import Appointment, AppointmentStatus, AppointmentType
from app.models.availability import AvailableSlot
from app.services.email import EmailService

from app.services.google_calendar_service import GoogleCalendarService

class SecretaryService:
    @staticmethod
    async def execute_tool(tool_name: str, args: Dict[str, Any], db: AsyncSession, session_id: str) -> Dict[str, Any]:
        """Enruta la ejecución de la herramienta a la función correspondiente."""
        if tool_name == "capture_lead":
            return await SecretaryService._tool_capture_lead(args, db, session_id)
        elif tool_name == "check_availability":
            return await SecretaryService._tool_check_availability(args)
        elif tool_name == "create_appointment":
            return await SecretaryService._tool_create_appointment(args, db)
        else:
            return {"error": f"Tool '{tool_name}' no reconocida."}

    @staticmethod
    async def _tool_capture_lead(args: Dict[str, Any], db: AsyncSession, session_id: str) -> Dict[str, Any]:
        """Guarda o actualiza un lead."""
        email = args.get("email", "").lower().strip()
        
        # Validación de email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return {"success": False, "error": "Email inválido", "message": "Por favor revisa el formato del email."}
        
        result = await db.execute(select(Lead).where(Lead.email == email))
        existing = result.scalars().first()
        
        if existing:
            # Actualizar datos faltantes
            if args.get("name") and not existing.name:
                existing.name = args["name"]
            if args.get("phone") and not existing.phone:
                existing.phone = args["phone"]
            if args.get("service_interest"):
                existing.service_interest = args["service_interest"]
            
            db.add(existing)
            await db.commit()
            return {
                "success": True,
                "is_returning_user": True,
                "lead_id": existing.id,
                "message": f"Información actualizada correctamente para {existing.name or email}."
            }
        
        # Si no existe, creamos
        lead = Lead(
            email=email,
            name=args.get("name"),
            phone=args.get("phone"),
            service_interest=args.get("service_interest"),
            initial_message=args.get("initial_message"),
            session_id=session_id
        )
        
        db.add(lead)
        await db.commit()
        await db.refresh(lead)
        
        # Obtener los emails de los abogados (administradores)
        from app.models.user import User
        from app.core.config import settings
        lawyers_result = await db.execute(select(User).where(User.role == "admin"))
        lawyers = lawyers_result.scalars().all()
        lawyer_emails = [l.email for l in lawyers] if lawyers else [settings.MAIL_FROM]
        
        # Enviar correo de bienvenida al nuevo prospecto
        import asyncio
        asyncio.create_task(
            EmailService.send_lead_welcome(
                email=lead.email,
                name=lead.name
            )
        )
        
        # Enviar alerta por correo a los abogados
        for l_email in lawyer_emails:
            asyncio.create_task(
                EmailService.send_lead_alert_to_lawyer(
                    lawyer_email=l_email,
                    lead_name=lead.name,
                    lead_email=lead.email,
                    phone=lead.phone,
                    service_interest=lead.service_interest,
                    initial_message=lead.initial_message
                )
            )
        
        return {
            "success": True,
            "is_returning_user": False,
            "lead_id": lead.id,
            "message": "Datos de contacto guardados exitosamente."
        }


    @staticmethod
    async def _tool_check_availability(args: Dict[str, Any]) -> Dict[str, Any]:
        """Retorna slots disponibles consultando Google Calendar."""
        try:
            date_from = args["date_from"]
            date_to = args["date_to"]
            
            slots = await GoogleCalendarService.get_available_slots(date_from, date_to)
            
            if not slots:
                return {
                    "success": True,
                    "available": False,
                    "slots": [],
                    "message": "No encontré disponibilidad en Google Calendar para esas fechas. Por favor intenta otro rango."
                }
            
            return {
                "success": True,
                "available": True,
                "slots": slots,
                "message": "He encontrado estos espacios disponibles en nuestro calendario de Google."
            }
        except Exception as e:
            return {"success": False, "error": f"Error al consultar Google Calendar: {str(e)}"}

    @staticmethod
    async def _tool_create_appointment(args: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Crea la cita en Google Calendar y registra el Lead/Cita localmente."""
        try:
            lead_email = args["lead_email"].lower()
            appt_date = args["appointment_date"]
            appt_time = args["appointment_time"]
            reason = args["reason"]
            
            # 1. Intentar crear en Google Calendar primero
            # Buscamos el ISO en los slots sugeridos o lo construimos
            # Para simplificar, construimos el ISO asumiendo la zona horaria de Colombia
            try:
                dt_str = f"{appt_date}T{appt_time}:00"
                # Validamos formato
                datetime.fromisoformat(dt_str)
            except ValueError:
                return {"success": False, "error": "Formato de fecha u hora inválido."}

            summary = f"Cita Star-Doc: {args.get('lead_name', lead_email)}"
            description = f"Motivo: {reason}\nAgendado vía Asistente IA STAR-DOC."
            
            google_result = await GoogleCalendarService.create_event(
                summary=summary,
                description=description,
                start_iso=dt_str,
                attendee_email=lead_email
            )
            
            if not google_result["success"]:
                return {
                    "success": False, 
                    "error": "google_api_error", 
                    "message": f"Hubo un problema con Google Calendar: {google_result.get('error')}"
                }

            # 2. Registrar en base de datos local para trazabilidad
            appointment = Appointment(
                lead_email=lead_email,
                lead_name=args.get("lead_name"),
                appointment_date=date.fromisoformat(appt_date),
                appointment_time=time.fromisoformat(appt_time),
                appointment_type=args.get("appointment_type", AppointmentType.VIDEO_CALL.value),
                reason=reason,
                meeting_link=google_result.get("meet_link")
            )
            appointment.generate_token()
            
            # Vincular con Lead si existe
            from sqlalchemy import select
            lead_result = await db.execute(select(Lead).where(Lead.email == lead_email))
            lead = lead_result.scalars().first()
            if lead:
                appointment.lead_id = lead.id
                lead.status = LeadStatus.APPOINTED.value
                db.add(lead)
            
            db.add(appointment)
            await db.commit()
            
            # 3. Preparar datos de la cita para el correo
            import asyncio
            confirm_data = {
                "name": args.get("lead_name") or lead_email,
                "date": appt_date,
                "time": appt_time,
                "type": appointment.appointment_type,
                "reason": reason,
                "meeting_link": google_result.get("meet_link"),
                "token": appointment.confirmation_token
            }
            
            # Obtener los emails de los abogados (administradores) para enviarles la alerta
            from app.models.user import User
            from app.core.config import settings
            lawyers_result = await db.execute(select(User).where(User.role == "admin"))
            lawyers = lawyers_result.scalars().all()
            lawyer_emails = [l.email for l in lawyers] if lawyers else [settings.MAIL_FROM]

            # Función asíncrona secuencial para enviar los correos sin colisiones SMTP
            async def send_all_emails():
                try:
                    logger.info(f"[SecretaryService] Iniciando envío secuencial de correos para cita de {lead_email}...")
                    # 1. Enviar confirmación al cliente/prospecto
                    await EmailService.send_appointment_confirmation(
                        email=lead_email,
                        subject=f"Confirmación: Asesoría Legal - {appt_date}",
                        template_body=confirm_data
                    )
                    
                    # 2. Delay de cortesía para no saturar la conexión SMTP de Gmail
                    await asyncio.sleep(1.2)
                    
                    # 3. Enviar alerta a los abogados administradores
                    for l_email in lawyer_emails:
                        await EmailService.send_appointment_alert_to_lawyer(
                            lawyer_email=l_email,
                            appt_details={
                                "name": confirm_data["name"],
                                "email": lead_email,
                                "date": confirm_data["date"],
                                "time": confirm_data["time"],
                                "type": confirm_data["type"],
                                "reason": confirm_data["reason"],
                                "meeting_link": confirm_data["meeting_link"]
                            }
                        )
                        await asyncio.sleep(0.5)
                    logger.info("[SecretaryService] Todos los correos de agendamiento se enviaron con éxito.")
                except Exception as e:
                    logger.error(f"[SecretaryService] Error en la tarea en segundo plano de envío de correos: {e}")

            # Lanzamos una única tarea en segundo plano
            asyncio.create_task(send_all_emails())

            # 4. Respuesta exitosa
            return {
                "success": True,
                "message": "¡Excelente! La cita ha sido agendada en Google Calendar. Recibirás una invitación por correo con el enlace de Google Meet.",
                "meet_link": google_result.get("meet_link")
            }
            
        except Exception as e:
            return {"success": False, "error": f"Error inesperado al crear la cita: {str(e)}"}

