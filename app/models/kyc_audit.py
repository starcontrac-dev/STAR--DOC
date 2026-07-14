from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime

class KycAudit(SQLModel, table=True):
    __tablename__ = "kyc_audits"

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: Optional[str] = Field(default=None, index=True) # ID del documento o contrato asociado
    full_name: str = Field(index=True)
    id_number: str = Field(index=True)
    status: str = Field(default="APROBADO") # APROBADO, RIESGO_MEDIO, RIESGO_ALTO, BLOQUEADO
    ofac_match: bool = Field(default=False)
    un_match: bool = Field(default=False)
    contraloria_match: bool = Field(default=False)
    procuraduria_match: bool = Field(default=False)
    details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
