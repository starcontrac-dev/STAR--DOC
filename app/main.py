
# --- Environment Loading ---
from dotenv import load_dotenv
load_dotenv()

# --- Standard Library Imports ---
import logging
import sys
import asyncio
from contextlib import asynccontextmanager

# --- Fix for Windows and Python 3.13+ event loop issues ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- Third-Party Imports ---
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- Local Application Imports ---
from app.core.config import settings
from app.database import connect_to_db, close_db_pool
from app.scheduler import start_scheduler, stop_scheduler
from app.exceptions.error_handler import add_exception_handlers

# --- Routers ---
from app.api.routers import auth, drive, ai, scheduling, frontend
from app.api.routers import templates, generation, validation
from app.api.routers import tts, skills, documents
from app.api.routers import metricas
from app.api.routers import ipfs
from app.api.routers import comparison
from app.api.routers import signatures, appointments, compliance, ocr, meetings

# --- Logging Config ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(settings.LOG_PATH),
        logging.StreamHandler()
    ]
)
# Silenciar logs informativos de APScheduler para evitar ruido constante en la terminal
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestiona el ciclo de vida de servicios como la BD, el scheduler y el cliente HTTPX.
    """
    # Validar seguridad de la SECRET_KEY
    if settings.SECRET_KEY == "DEVELOPMENT_INSECURE_SECRET_KEY":
        logger.warning(
            "⚠️  ALERTA DE SEGURIDAD CRÍTICA: Se está utilizando la SECRET_KEY por defecto insegura. "
            "Por favor, configure una SECRET_KEY robusta en el archivo .env para proteger tokens y cifrado de datos."
        )

    # Inicializar pool de conexiones a la base de datos
    try:
        await connect_to_db()
        logger.info("Pool de conexiones a la base de datos inicializado.")
    except Exception as e:
        logger.error(f"No se pudo inicializar la base de datos en el arranque: {e}")

    # Inicializar Redis
    try:
        from app.core.redis_client import redis_manager
        redis_health = await redis_manager.health_check()
        if redis_health["status"] == "healthy":
            logger.info(f"✅ Redis conectado v{redis_health['version']}")
        else:
            logger.warning(f"⚠️ Redis no disponible: {redis_health.get('error')}")
    except Exception as e:
        logger.error(f"Error inicializando Redis en el arranque: {e}")

    # Iniciar el scheduler de tareas programadas
    try:
        start_scheduler()
    except Exception as e:
        logger.error(f"No se pudo iniciar el scheduler: {e}")

    # Configurar cliente HTTPX global
    app.state.http_client = httpx.AsyncClient()
    
    try:
        yield
    finally:
        # Cerrar cliente HTTPX
        await app.state.http_client.aclose()
        logger.info("Cliente HTTPX cerrado.")

        # Cerrar conexiones de Redis
        try:
            from app.core.redis_client import redis_manager
            await redis_manager.close_all()
            logger.info("Pool de conexiones Redis cerrado.")
        except Exception as e:
            logger.error(f"Error cerrando el pool de conexiones Redis: {e}")

        # Detener el scheduler
        try:
            stop_scheduler()
        except Exception as e:
            logger.error(f"Error deteniendo el scheduler: {e}")

        # Cerrar pool de BD
        try:
            await close_db_pool()
            logger.info("Pool de conexiones a la base de datos cerrado.")
        except Exception as e:
            logger.error(f"Error cerrando el pool de la base de datos: {e}")

        # Cerrar motor Playwright (si se usó)
        try:
            from app.core.browser_engine import playwright_engine
            await playwright_engine.close()
        except Exception as e:
            logger.error(f"Error cerrando Playwright: {e}")

# --- API Documentation Metadata ---
tags_metadata = [
    {
        "name": "Authentication",
        "description": "Gestión de usuarios, registro y acceso mediante JWT, OAuh2 (Google) y Web3 (Wallets).",
    },
    {
        "name": "Legal AI Engine",
        "description": "El cerebro de STAR-DOC. Incluye proxy Gemini, procesamiento de lenguaje natural y extracción de texto legal.",
    },
    {
        "name": "Document Automation",
        "description": "Motores de generación de documentos unitarios y masivos (batch) con validación inteligente.",
    },
    {
        "name": "Templates Engine",
        "description": "Sistema de gestión, edición y versionamiento de plantillas legales (.docx y .md).",
    },
    {
        "name": "Cloud Integrations",
        "description": "Conectores directos con servicios en la nube de Google (Drive, Sheets, Docs).",
    },
    {
        "name": "Task Scheduler",
        "description": "Programación de tareas automáticas, recordatorios y flujos de trabajo diferidos.",
    },
    {
        "name": "UI & Navigation",
        "description": "Renderizado de interfaces de usuario y navegación principal de la plataforma.",
    },
    {
        "name": "Data & Metrics",
        "description": "Telemetría, estadísticas de uso de IA y paneles de rendimiento del sistema.",
    },
    {
        "name": "TTS - Text to Speech",
        "description": "Generación de audio a partir de texto para accesibilidad y flujos manos libres.",
    },
    {
        "name": "IPFS & Web3",
        "description": "Almacenamiento inmutable en IPFS, encriptación AES-256-GCM y certificación de documentos legales.",
    }
]

# --- App Initialization ---
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="""
    🚀 **STAR-DOC API**: Sistema de Inteligencia Legal de Grado Empresarial.
    
    Esta API proporciona capacidades avanzadas de:
    *   **IA Generativa** para auditoría y creación de contratos.
    *   **Automatización Masiva** de documentos legales.
    *   **Integración Web3** para identidad digital.
    *   **RAG (Retrieval Augmented Generation)** para bóvedas de conocimiento jurídico.
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan
)

# --- SlowAPI Limiter ---
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Middlewares de Seguridad ---
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders

class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                headers.append("X-Content-Type-Options", "nosniff")
                headers.append("X-Frame-Options", "SAMEORIGIN")
                headers.append("X-XSS-Protection", "1; mode=block")
                headers.append("Content-Security-Policy", "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; script-src * 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline'; font-src * data:; img-src * data: blob:;")
            await send(message)
            
        await self.app(scope, receive, send_wrapper)

# --- Configuración de orígenes autorizados para CORS ---
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Exception Handlers ---
add_exception_handlers(app)

# --- Static Files ---
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
app.mount("/output", StaticFiles(directory=settings.OUTPUT_DIR), name="output")

# --- Include Routers ---
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(generation.router)
app.include_router(validation.router)
app.include_router(drive.router)
app.include_router(ai.router)
app.include_router(scheduling.router)
app.include_router(frontend.router)
app.include_router(tts.router)
app.include_router(skills.router)
app.include_router(documents.router)
app.include_router(metricas.router)
app.include_router(ipfs.router)
app.include_router(comparison.router)
app.include_router(signatures.router)
app.include_router(appointments.router)
app.include_router(compliance.router)
app.include_router(ocr.router)
app.include_router(meetings.router)


logger.info("Aplicación Star-Doc iniciada y lista para recibir solicitudes.")
