from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class KycAuditRequest(BaseModel):
    full_name: str = Field(..., description="Nombre completo de la persona natural o razón social de la persona jurídica")
    id_number: str = Field(..., description="Número de identificación (Cédula de Ciudadanía, Cédula de Extranjería o NIT)")
    document_id: Optional[str] = Field(None, description="ID del documento en STAR-DOC opcional al que se asocia la auditoría")

class SanctionMatch(BaseModel):
    source: str = Field(..., description="Fuente de la coincidencia (OFAC, ONU, Contraloría, Procuraduría)")
    type: str = Field(..., description="Tipo de antecedente o sanción hallada")
    entity_or_person: str = Field(..., description="Nombre del registro coincidente en la lista")
    document_matched: Optional[str] = Field(None, description="Identificación encontrada")
    description: Optional[str] = Field(None, description="Detalle del hallazgo o motivo de sanción")
    date: Optional[str] = Field(None, description="Fecha de efectos jurídicos o publicación de la sanción")
    severity: str = Field(..., description="Severidad (ALTO, MEDIO, INFORMATIVO)")

class KycAuditResponse(BaseModel):
    success: bool
    audit_id: Optional[int] = None
    full_name: str
    id_number: str
    status: str = Field(..., description="APROBADO, RIESGO_MEDIO, RIESGO_ALTO, BLOQUEADO")
    verdict: str = Field(..., description="Veredicto legal justificado detallando el nivel de riesgo según SARLAFT/SAGRILAFT")
    ofac_match: bool
    un_match: bool
    contraloria_match: bool
    procuraduria_match: bool
    matches: List[SanctionMatch] = []
    created_at: datetime

class SyncListsResponse(BaseModel):
    success: bool
    message: str
    ofac_records_count: int
    un_records_count: int
    updated_at: datetime
