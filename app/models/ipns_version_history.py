"""Modelo SQLModel para registrar el historial de versiones de llaves mutables de IPNS.

Permite realizar trazabilidad jurídica y auditoría forense sobre qué CIDs inmutables 
han sido publicados históricamente bajo cada clave mutable IPNS.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

class IPNSVersionHistory(SQLModel, table=True):
    """Historial de publicaciones y versiones asociadas a una clave IPNS."""
    __tablename__ = "ipns_version_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Llave foránea hacia ipns_keys.id
    ipns_key_id: int = Field(foreign_key="ipns_keys.id", index=True)
    
    # El CID inmutable de destino de esta versión
    cid: str = Field(index=True)
    
    # Marca de tiempo de cuándo se publicó la versión
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    # El ID del usuario que realizó la publicación (opcional)
    user_id: Optional[int] = Field(default=None, index=True)
