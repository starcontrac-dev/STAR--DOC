from datetime import datetime
from typing import Optional, List
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

class WebhookSubscription(SQLModel, table=True):
    """Suscripción de webhook para notificaciones de eventos IPFS."""
    __tablename__ = "webhook_subscriptions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    url: str  # URL de destino del webhook
    secret: Optional[str] = None  # Para firmar el payload (HMAC-SHA256)
    events: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )  # Eventos: ["upload", "verify", "download", "audit_pack", "archive"]
    user_id: Optional[int] = Field(default=None, index=True)
    is_active: bool = Field(default=True)
    last_triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
