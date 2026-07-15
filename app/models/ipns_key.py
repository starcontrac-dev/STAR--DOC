from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

class IPNSKey(SQLModel, table=True):
    """Registro de claves IPNS activas para republishing automático."""
    __tablename__ = "ipns_keys"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    key_name: str = Field(index=True, unique=True)
    ipns_id: str = Field(index=True)  # El PeerID/KeyID (k51...)
    current_cid: Optional[str] = None  # Último CID publicado
    user_id: Optional[int] = Field(default=None, index=True)
    is_active: bool = Field(default=True)
    last_published_at: Optional[datetime] = None
    last_republished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
