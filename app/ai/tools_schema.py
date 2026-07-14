"""
Definición de las Herramientas (Function Calling) para el Secretario IA.
Utiliza el estándar de schema de Gemini/OpenAI para la inyección en el modelo.
"""

SECRETARY_TOOLS = [
    {
        "name": "capture_lead",
        "description": "Guarda la información de un visitante interesado en los servicios o actualiza su perfil. ÚSALA de forma proactiva en cuanto tengas email + nombre (o al menos uno de los dos) y el servicio que busca.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email del usuario. Valida el formato antes de llamar."
                },
                "name": {
                    "type": "string",
                    "description": "Nombre completo o solo el primer nombre del usuario."
                },
                "phone": {
                    "type": "string",
                    "description": "Teléfono de contacto si el usuario lo proporcionó. Opcional."
                },
                "service_interest": {
                    "type": "string",
                    "description": "Breve descripción del servicio que busca. Ej: 'Consulta sobre contrato laboral'."
                },
                "initial_message": {
                    "type": "string",
                    "description": "Resumen de la consulta inicial o caso del usuario para dar contexto al abogado."
                }
            },
            "required": ["email", "service_interest"]
        }
    },
    {
        "name": "check_availability",
        "description": "Consulta los horarios disponibles para citas (meetings) en una fecha específica o rango. ÚSALA siempre ANTES de proponer posibles horarios al usuario. Nunca inventes disponibilidad.",
        "parameters": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Fecha de inicio de la búsqueda en formato YYYY-MM-DD. Ej: '2026-04-15'"
                },
                "date_to": {
                    "type": "string",
                    "description": "Fecha de fin de la búsqueda en formato YYYY-MM-DD. Si solo es un día, pasa el mismo valor de date_from."
                }
            },
            "required": ["date_from", "date_to"]
        }
    },
    {
        "name": "create_appointment",
        "description": "Crea y confirma una cita en el sistema y automáticamente dispara un email de confirmación y enlace. ÚSALA SÓLO cuando el usuario haya aceptado una fecha y hora sugerida de las opciones previas y tengas su email.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_email": {
                    "type": "string",
                    "description": "Email del prospecto. Indispensable para confirmar la cita."
                },
                "lead_name": {
                    "type": "string",
                    "description": "Nombre del prospecto."
                },
                "appointment_date": {
                    "type": "string",
                    "description": "Fecha exacta acordada en formato YYYY-MM-DD."
                },
                "appointment_time": {
                    "type": "string",
                    "description": "Hora exacta acordada en formato HH:MM (24 hrs). Ej '14:30'."
                },
                "appointment_type": {
                    "type": "string",
                    "description": "Modalidad de la reunión.",
                    "enum": ["video_call", "phone_call", "in_person", "whatsapp"]
                },
                "reason": {
                    "type": "string",
                    "description": "Motivo de la consulta y detalles relevantes para el asesor."
                }
            },
            "required": ["lead_email", "appointment_date", "appointment_time", "reason"]
        }
    }
]

# Estructura wrapper para Gemini (Tool con functionDeclarations)
gemini_secretary_tools = {
    "function_declarations": SECRETARY_TOOLS
}
