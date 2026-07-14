"""Modelo SQLModel para auditorías/expedientes empaquetados en IPFS."""
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON


class IPFSAudit(SQLModel, table=True):
    """Representa un paquete de auditoría que agrupa múltiples documentos en un directorio IPFS."""
    __tablename__ = "ipfs_audits"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    ipfs_cid: str = Field(index=True, unique=True)
    classification: str = Field(default="public")  # public | confidential | chain_of_custody
    
    # IDs de los documentos pertenecientes a esta auditoría (guardados como JSON)
    document_ids: List[int] = Field(default_factory=list, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
