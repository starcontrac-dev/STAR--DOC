from typing import Optional, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, JSON, Relationship

class UserDocument(SQLModel, table=True):
    __tablename__ = "user_documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    
    filename: str = Field(index=True)
    content_text: str = Field(default="") # El texto extraído
    
    # Metadatos extraídos por IA opcionales
    metadata_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    
    # --- Workflow de Aprobación Documental ---
    # Estados: draft | pending_approval | approved | rejected | signed
    status: str = Field(default="draft", index=True)
    comments: Optional[str] = Field(default=None)
    reviewed_by_id: Optional[int] = Field(default=None, foreign_key="users.id", nullable=True)
    reviewed_at: Optional[datetime] = Field(default=None)

    # --- Workflow de Edición Colaborativa en la Nube (CryptPad.fr) ---
    cryptpad_share_url: Optional[str] = Field(default=None, nullable=True)
    is_collaborative: bool = Field(default=False, index=True)
