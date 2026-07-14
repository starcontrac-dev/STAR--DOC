from typing import Optional, Dict, Any
from datetime import datetime
import enum
from sqlmodel import SQLModel, Field, JSON, Column

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    full_name: str
    email: str = Field(unique=True, index=True)
    hashed_password: str
    disabled: bool = Field(default=False)
    
    is_verified: bool = Field(default=False)
    verification_token: Optional[str] = Field(default=None, index=True)
    reset_password_token: Optional[str] = Field(default=None, index=True)
    reset_token_expires: Optional[datetime] = Field(default=None)
    
    # JSON fields need sa_column for Postgres JSONB compatibility if we want strict typing or specific DB types
    # For simplicity with SQLModel we can use sa_type or Column(JSON)
    google_credentials: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    oauth_state: Optional[str] = Field(default=None, index=True)
    role: str = Field(default="user", nullable=False)
    
    # Campos agregados para Notificaciones 2026
    phone: Optional[str] = Field(default=None)
    notification_preferences: Optional[Dict[str, Any]] = Field(default={"email": True}, sa_column=Column(JSON))

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"
