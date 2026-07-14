from pydantic_settings import BaseSettings
from pydantic import computed_field
import os
from typing import Optional, Dict, Any
import json

class Settings(BaseSettings):
    PROJECT_NAME: str = "Star-Doc"
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    
    # Directorios
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    TEMPLATES_DIR: str = os.path.join(BASE_DIR, "templates")
    STATIC_DIR: str = os.path.join(BASE_DIR, "static")
    
    # Configuración dinámica (se puede sobreescribir con env vars)
    TEMPLATE_DIR_NAME: str = "plantillas"
    OUTPUT_DIR_NAME: str = "output"
    
    @computed_field
    @property
    def PLANTILLAS_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, self.TEMPLATE_DIR_NAME)
        
    @computed_field
    @property
    def OUTPUT_DIR(self) -> str:
        return os.path.join(self.BASE_DIR, self.OUTPUT_DIR_NAME)

    @computed_field
    @property
    def TEMPLATES_JSON_PATH(self) -> str:
        return os.path.join(self.BASE_DIR, 'templates.json')
    
    @computed_field
    @property
    def LOG_PATH(self) -> str:
        return os.path.join(self.BASE_DIR, 'star-doc.log')

    # Security
    ENV: str = os.getenv("ENV", "development")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "DEVELOPMENT_INSECURE_SECRET_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS", 
        "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://localhost:5173"
    )
    
    @computed_field
    @property
    def GOOGLE_CLIENT_SECRETS_FILE(self) -> str:
        env_secrets_file = os.getenv("GOOGLE_CLIENT_SECRETS_FILE")
        if env_secrets_file:
            return env_secrets_file
        return os.path.join(self.BASE_DIR, 'credentials.json')

    REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"
    
    # Gemini
    GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")

    @computed_field
    @property
    def GEMINI_API_KEYS(self) -> list[str]:
        """Retorna una lista de todas las claves de Gemini configuradas, ignorando placeholders."""
        keys = []
        primary = os.getenv("GEMINI_API_KEY")
        if primary and "your_gemini" not in primary.lower():
            keys.append(primary)
        
        for i in range(2, 11):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if key and "your_gemini" not in key.lower():
                keys.append(key)
        
        return keys

    # Mail Config (Sincronizado con .env)
    # Mail Config (Sincronizado con .env)
    from pydantic import Field
    MAIL_USERNAME: str = Field(default="tu_email@example.com", alias="SMTP_USERNAME")
    MAIL_PASSWORD: str = Field(default="tu_contraseña", alias="SMTP_PASSWORD")
    MAIL_FROM: str = Field(default="tu_email@example.com", alias="SMTP_FROM_EMAIL")
    MAIL_PORT: int = Field(default=587, alias="SMTP_PORT")
    MAIL_SERVER: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    MAIL_STARTTLS: bool = Field(default=True, alias="SMTP_USE_TLS")
    MAIL_SSL_TLS: bool = Field(default=False, alias="SMTP_USE_SSL")
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True

    # Database
    DATABASE_URL: Optional[str] = None
    POSTGRES_HOST: Optional[str] = None
    POSTGRES_PORT: Optional[str] = None
    POSTGRES_DATABASE: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None

    # Redis Config
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379/0"

    # Google Calendar
    GOOGLE_CLIENT_ID: Optional[str] = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: Optional[str] = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REFRESH_TOKEN: Optional[str] = os.getenv("GOOGLE_REFRESH_TOKEN")
    GOOGLE_CALENDAR_ID: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    
    # Pinata Config (Leido desde .env por Pydantic)
    PINATA_JWT: Optional[str] = None
    PINATA_GATEWAY: str = "https://gateway.pinata.cloud"

    # Jitsi Meet
    JITSI_DOMAIN: str = os.getenv("JITSI_DOMAIN", "meet.jit.si")
    JITSI_USE_JWT: bool = os.getenv("JITSI_USE_JWT", "False").lower() in ("true", "1", "yes")
    JITSI_APP_ID: Optional[str] = os.getenv("JITSI_APP_ID", None)
    JITSI_SECRET: Optional[str] = os.getenv("JITSI_SECRET", None)

    # SSRF Protection
    ALLOW_PRIVATE_WEBHOOKS: bool = False

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"
    }

# Instancia global
settings = Settings()

# Validación Crítica de Seguridad en Producción
if settings.ENV.lower() == "production" and settings.SECRET_KEY == "DEVELOPMENT_INSECURE_SECRET_KEY":
    raise ValueError(
        "❌ ERROR DE SEGURIDAD CRÍTICO: No se permite iniciar la aplicación en entorno 'production' "
        "utilizando la SECRET_KEY por defecto insegura. Por favor, defina una SECRET_KEY robusta en el archivo .env."
    )

# Cargar configuración legacy de config.json si existe para sobreescribir defaults no críticos
config_path = os.path.join(settings.BASE_DIR, 'config.json')
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            legacy_config = json.load(f)
            if "template_dir" in legacy_config:
                settings.TEMPLATE_DIR_NAME = legacy_config["template_dir"]
            if "output_dir" in legacy_config:
                settings.OUTPUT_DIR_NAME = legacy_config["output_dir"]
    except Exception:
        pass

# Asegurar directorios
for dir_path in [settings.OUTPUT_DIR, settings.PLANTILLAS_DIR, settings.STATIC_DIR, settings.TEMPLATES_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
