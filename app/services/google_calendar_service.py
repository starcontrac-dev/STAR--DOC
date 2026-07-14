import os
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import List, Dict, Any, Optional
import pytz
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import asyncio
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.core.config import settings

# Configuración de Logger
logger = logging.getLogger(__name__)

# Configuración de Zona Horaria (Colombia)
COLOMBIA_TZ = pytz.timezone("America/Bogota")

class GoogleCalendarService:
    """
    Servicio profesional para interactuar con Google Calendar API.
    Maneja disponibilidad real, agendamiento, lectura, reprogramación y cancelación.
    """
    
    _SCOPES = ['https://www.googleapis.com/auth/calendar']

    @staticmethod
    def _get_credentials() -> Credentials:
        """Obtiene credenciales OAuth2 usando el Refresh Token."""
        creds_data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "refresh_token": settings.GOOGLE_REFRESH_TOKEN,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        
        if not creds_data["refresh_token"] or not creds_data["client_id"]:
            logger.error("Credenciales incompletas en las variables de entorno.")
            raise ValueError("Faltan credenciales de Google (CLIENT_ID o REFRESH_TOKEN) en el .env")

        creds = Credentials.from_authorized_user_info(creds_data, GoogleCalendarService._SCOPES)

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refrescando el token de Google: {e}")
                raise
            
        return creds

    @staticmethod
    async def get_service():
        """Construye el cliente de la API de Google Calendar."""
        def _build_service():
            creds = GoogleCalendarService._get_credentials()
            # cache_discovery=False evita el warning de oauth2client y problemas de IO concurrentes
            return build('calendar', 'v3', credentials=creds, cache_discovery=False)
            
        return await asyncio.to_thread(_build_service)

    @staticmethod
    async def get_available_slots(
        date_from: str, 
        date_to: str, 
        work_start_hour: int = 9, 
        work_end_hour: int = 18, 
        slot_duration_minutes: int = 60,
        max_results: int = 3
    ) -> List[Dict[str, str]]:
        """
        Calcula slots disponibles cruzando el horario laboral flexible con los eventos de Calendar.
        Mantiene compatibilidad hacia atrás manteniendo los valores por defecto originales.
        """
        try:
            service = await GoogleCalendarService.get_service()
            calendar_id = settings.GOOGLE_CALENDAR_ID
            
            # Parsear fechas y asegurar zona horaria
            start_dt = COLOMBIA_TZ.localize(datetime.fromisoformat(date_from).replace(hour=0, minute=0, second=0))
            end_dt = COLOMBIA_TZ.localize(datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59))
            
            # Consultar FreeBusy
            body = {
                "timeMin": start_dt.isoformat(),
                "timeMax": end_dt.isoformat(),
                "timeZone": "America/Bogota",
                "items": [{"id": calendar_id}]
            }
            
            query_request = service.freebusy().query(body=body)
            fb_result = await asyncio.to_thread(query_request.execute)
            
            busy_periods = fb_result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
            
            # Horario laboral parametrizado
            working_start = dt_time(work_start_hour, 0)
            working_end = dt_time(work_end_hour, 0)
            slot_duration = timedelta(minutes=slot_duration_minutes)
            
            available_slots = []
            current_day = start_dt
            
            # Calculamos límite en el tiempo (para no ofrecer reuniones en los próximos 60 min)
            buffer_time = datetime.now(COLOMBIA_TZ) + timedelta(hours=1)
            
            while current_day <= end_dt:
                if current_day.weekday() < 5:  # Lunes a Viernes
                    day_start = COLOMBIA_TZ.localize(datetime.combine(current_day.date(), working_start))
                    day_end = COLOMBIA_TZ.localize(datetime.combine(current_day.date(), working_end))
                    
                    temp_slot_start = day_start
                    while temp_slot_start + slot_duration <= day_end:
                        temp_slot_end = temp_slot_start + slot_duration
                        
                        if temp_slot_start < buffer_time:
                            temp_slot_start += slot_duration
                            continue

                        # Evaluar colisiones de manera asertiva
                        is_busy = any(
                            temp_slot_start < datetime.fromisoformat(p["end"].replace('Z', '+00:00')).astimezone(COLOMBIA_TZ) 
                            and temp_slot_end > datetime.fromisoformat(p["start"].replace('Z', '+00:00')).astimezone(COLOMBIA_TZ)
                            for p in busy_periods
                        )
                        
                        if not is_busy:
                            available_slots.append({
                                "date": temp_slot_start.date().isoformat(),
                                "time": temp_slot_start.time().strftime("%H:%M"),
                                "iso": temp_slot_start.isoformat()
                            })
                        
                        temp_slot_start += slot_duration
                
                current_day += timedelta(days=1)
                
            return available_slots[:max_results]
        
        except HttpError as error:
            logger.error(f"Error consultando FreeBusy: {error}")
            return []
        except Exception as e:
            logger.error(f"Error inesperado procesando slots: {e}")
            return []

    @staticmethod
    async def create_event(
        summary: str,
        description: str,
        start_iso: str,
        attendee_email: str,
        duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """Crea un evento en Google Calendar con enlace de Meet."""
        try:
            service = await GoogleCalendarService.get_service()
            calendar_id = settings.GOOGLE_CALENDAR_ID
            
            naive_dt = datetime.fromisoformat(start_iso)
            start_dt = COLOMBIA_TZ.localize(naive_dt) if naive_dt.tzinfo is None else naive_dt.astimezone(COLOMBIA_TZ)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            event = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Bogota'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Bogota'},
                'attendees': [{'email': attendee_email}],
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"meet-{int(datetime.now().timestamp())}",
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},
                        {'method': 'popup', 'minutes': 30},
                    ],
                },
            }
            
            insert_request = service.events().insert(
                calendarId=calendar_id,
                body=event,
                conferenceDataVersion=1,
                sendUpdates='all'
            )
            event_result = await asyncio.to_thread(insert_request.execute)
            
            logger.info(f"Evento {event_result.get('id')} creado con éxito.")
            return {
                "success": True,
                "event_id": event_result.get("id"),
                "html_link": event_result.get("htmlLink"),
                "meet_link": event_result.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri")
            }
        except HttpError as error:
            logger.error(f"Error creando el evento: {error}")
            return {"success": False, "error": str(error)}

    # ==========================================
    # NUEVAS FUNCIONALIDADES (API MAS AMPLIA)
    # ==========================================

    @staticmethod
    async def list_upcoming_events(max_results: int = 10, time_min_iso: Optional[str] = None) -> Dict[str, Any]:
        """Lista los próximos eventos agendados en el calendario."""
        try:
            service = await GoogleCalendarService.get_service()
            calendar_id = settings.GOOGLE_CALENDAR_ID
            
            if not time_min_iso:
                time_min_iso = datetime.now(COLOMBIA_TZ).isoformat()
            else:
                naive_dt = datetime.fromisoformat(time_min_iso)
                time_min_iso = (COLOMBIA_TZ.localize(naive_dt) if naive_dt.tzinfo is None else naive_dt.astimezone(COLOMBIA_TZ)).isoformat()

            request = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min_iso,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            )
            events_result = await asyncio.to_thread(request.execute)
            
            return {
                "success": True, 
                "events": events_result.get('items', [])
            }
        except HttpError as error:
            logger.error(f"Error listando eventos: {error}")
            return {"success": False, "error": str(error)}

    @staticmethod
    async def cancel_event(event_id: str) -> Dict[str, Any]:
        """Cancela/Elimina un evento existente notificando al usuario."""
        try:
            service = await GoogleCalendarService.get_service()
            request = service.events().delete(
                calendarId=settings.GOOGLE_CALENDAR_ID,
                eventId=event_id,
                sendUpdates='all' # Avisa al invitado de la cancelación
            )
            await asyncio.to_thread(request.execute)
            logger.info(f"Evento {event_id} cancelado correctamente.")
            return {"success": True, "message": "Evento cancelado exitosamente."}
        except HttpError as error:
            logger.error(f"Error cancelando evento {event_id}: {error}")
            return {"success": False, "error": str(error)}

    @staticmethod
    async def reschedule_event(event_id: str, new_start_iso: str, duration_minutes: int = 60) -> Dict[str, Any]:
        """Reprograma un evento cambiando su fecha/hora y notificando a los invitados."""
        try:
            service = await GoogleCalendarService.get_service()
            calendar_id = settings.GOOGLE_CALENDAR_ID
            
            # 1. Obtener el evento actual
            get_request = service.events().get(calendarId=calendar_id, eventId=event_id)
            event = await asyncio.to_thread(get_request.execute)
            
            # 2. Calcular nuevas fechas
            naive_dt = datetime.fromisoformat(new_start_iso)
            start_dt = COLOMBIA_TZ.localize(naive_dt) if naive_dt.tzinfo is None else naive_dt.astimezone(COLOMBIA_TZ)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            # 3. Actualizar el cuerpo del evento
            event['start'] = {'dateTime': start_dt.isoformat(), 'timeZone': 'America/Bogota'}
            event['end'] = {'dateTime': end_dt.isoformat(), 'timeZone': 'America/Bogota'}
            
            # 4. Enviar actualización
            update_request = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendUpdates='all' # Informa el cambio de hora
            )
            updated_event = await asyncio.to_thread(update_request.execute)
            
            logger.info(f"Evento {event_id} reprogramado con éxito.")
            return {
                "success": True,
                "event_id": updated_event.get("id"),
                "html_link": updated_event.get("htmlLink")
            }
        except HttpError as error:
            logger.error(f"Error reprogramando evento {event_id}: {error}")
            return {"success": False, "error": str(error)}