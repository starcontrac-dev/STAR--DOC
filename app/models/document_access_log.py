"""Modelo SQLModel para el registro de cadena de custodia de documentos en IPFS."""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class DocumentAccessLog(SQLModel, table=True):
    """Log de accesos y verificaciones para la cadena de custodia de evidencia legal."""
    __tablename__ = "document_access_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    ipfs_cid: str = Field(index=True)
    user_id: Optional[int] = Field(default=None, index=True)
    username: Optional[str] = Field(default="Anonimo")
    action: str = Field(index=True)  # download | verify | certificate_view
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
