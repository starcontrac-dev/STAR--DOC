"""
Modelo SQLModel para registrar tareas de subida diferida (colas de reintento) a IPFS.
Garantiza robustez e integridad ante micro-cortes de red de los nodos IPFS.
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class IPFSPendingTask(SQLModel, table=True):
    """Registro de tareas pendientes de IPFS con número de reintentos y logs."""
    __tablename__ = "ipfs_pending_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Ruta del archivo a subir
    file_path: str = Field(nullable=False)
    
    # Metadatos del documento
    classification: str = Field(default="public")  # public | confidential | chain_of_custody
    user_id: Optional[int] = Field(default=None, index=True)
    document_id: Optional[int] = Field(default=None, index=True)
    signature_request_id: Optional[int] = Field(default=None, index=True)
    
    # Control de la cola de reintentos
    retry_count: int = Field(default=0, index=True)
    max_retries: int = Field(default=3)
    status: str = Field(default="pending", index=True)  # pending | processing | completed | failed
    last_error: Optional[str] = Field(default=None, nullable=True)
    
    # Fechas
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
