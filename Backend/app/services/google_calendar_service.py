import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

def parse_fecha_hora(fecha_hora_str: str) -> datetime:
    """
    Intenta parsear un string de fecha/hora en varios formatos.
    Si falla, retorna por defecto mañana a las 09:00.
    """
    if not fecha_hora_str:
        ahora = datetime.now()
        mañana = ahora + timedelta(days=1)
        return mañana.replace(hour=9, minute=0, second=0, microsecond=0)

    # Limpiar posibles comillas u otros caracteres
    fecha_hora_str = fecha_hora_str.strip().replace('"', '').replace("'", "")

    # Si es solo una fecha (ej: 2026-06-08 o 08-06-2026)
    is_date_only = len(fecha_hora_str) == 10

    # Intenta ISO completo o fecha sola
    try:
        dt = datetime.fromisoformat(fecha_hora_str)
        if is_date_only:
            dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
        return dt
    except Exception:
        pass

    # Formatos comunes en español/inglés
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y"
    ):
        try:
            dt = datetime.strptime(fecha_hora_str, fmt)
            if "%H" not in fmt or is_date_only:
                dt = dt.replace(hour=9, minute=0, second=0, microsecond=0)
            return dt
        except Exception:
            continue

    # Fallback final: mañana a las 9 am
    ahora = datetime.now()
    mañana = ahora + timedelta(days=1)
    return mañana.replace(hour=9, minute=0, second=0, microsecond=0)


class GoogleCalendarService:
    def __init__(self):
        # Determinar la ruta del archivo de credenciales
        env_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
        
        # Buscar en el Backend/ o directorio actual
        base_dir = Path(__file__).resolve().parents[2]  # Backend/
        self.credentials_path = base_dir / env_file
        
        if not self.credentials_path.exists():
            # Intentar como ruta directa
            self.credentials_path = Path(env_file)

        self.service = None
        self.enabled = False

        if self.credentials_path.exists():
            try:
                SCOPES = ['https://www.googleapis.com/auth/calendar']
                self.creds = service_account.Credentials.from_service_account_file(
                    str(self.credentials_path), scopes=SCOPES
                )
                self.service = build('calendar', 'v3', credentials=self.creds)
                self.enabled = True
                logger.info(f"Google Calendar Service habilitado con credenciales de: {self.credentials_path}")
                print(f"[CalendarService] Google Calendar habilitado usando: {self.credentials_path}")
            except Exception as e:
                logger.warning(f"Error cargando credenciales de Google Calendar: {e}")
                print(f"[CalendarService] Advertencia: Error autorizando con {self.credentials_path}: {e}")
        else:
            logger.info("Google Calendar Service en modo SIMULADO (no se encontró credentials.json).")
            print(f"[CalendarService] Modo SIMULADO. Coloque un archivo de credenciales en: {self.credentials_path.absolute()} para habilitar el servicio real.")

    def create_reminder_event(self, tramite: str, fecha_hora_str: str, email: str, documentos: str) -> dict:
        """
        Crea un evento en el calendario de la Service Account e invita al usuario.
        """
        dt_start = parse_fecha_hora(fecha_hora_str)
        dt_end = dt_start + timedelta(minutes=30)

        start_iso = dt_start.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = dt_end.strftime("%Y-%m-%dT%H:%M:%S")

        description = f"Recordatorio automático de ChileAtiende.\n\n"
        description += f"Trámite: {tramite}\n\n"
        if documentos:
            description += f"Documentos / Requisitos necesarios:\n{documentos}\n"

        if not self.enabled or self.service is None:
            # Modo simulado
            print(f"[CalendarService] [SIMULADO] Creando evento para {email} sobre '{tramite}' el {start_iso}")
            return {
                "status": "success_mock",
                "message": f"✅ (Modo de prueba) Recordatorio simulado con éxito. Se enviaría una invitación a {email} para el {dt_start.strftime('%d/%m/%Y a las %H:%M')}.",
                "event_id": "mock_event_123456",
                "htmlLink": "https://calendar.google.com/calendar/r"
            }

        try:
            event = {
                'summary': f'Trámite: {tramite}',
                'location': 'Oficina de ChileAtiende / Registro Civil',
                'description': description,
                'start': {
                    'dateTime': start_iso,
                    'timeZone': 'America/Santiago',
                },
                'end': {
                    'dateTime': end_iso,
                    'timeZone': 'America/Santiago',
                },
            }

            # Insertar directamente en el calendario del usuario (debe estar compartido con la Cuenta de Servicio)
            created_event = self.service.events().insert(
                calendarId=email,
                body=event
            ).execute()

            print(f"[CalendarService] Evento creado con éxito: {created_event.get('htmlLink')}")
            return {
                "status": "success",
                "message": f"✅ Recordatorio agendado con éxito directamente en tu calendario ({email}) para el {dt_start.strftime('%d/%m/%Y a las %H:%M')}.",
                "event_id": created_event.get("id"),
                "htmlLink": created_event.get("htmlLink")
            }
        except Exception as e:
            logger.error(f"Error creando evento en Google Calendar: {e}")
            print(f"[CalendarService] Error creando evento en Google Calendar: {e}")
            
            err_msg = str(e)
            if "not found" in err_msg.lower() or "forbidden" in err_msg.lower() or "access" in err_msg.lower() or "404" in err_msg or "403" in err_msg:
                sa_email = self.creds.service_account_email if hasattr(self, 'creds') else 'correo de tu cuenta de servicio'
                user_friendly_msg = (
                    f"❌ No se pudo acceder al calendario de {email}. "
                    f"Por favor, comparte tu Google Calendar con la cuenta de servicio "
                    f"({sa_email}) con permisos de 'Realizar cambios en eventos'."
                )
            else:
                user_friendly_msg = f"❌ Error al crear el evento en Google Calendar: {err_msg}"

            return {
                "status": "error",
                "message": user_friendly_msg,
                "event_id": None,
                "htmlLink": None
            }
