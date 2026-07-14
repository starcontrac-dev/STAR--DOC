from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class OcrResponse(BaseModel):
    success: bool = Field(..., description="Indica si la extracción de texto y variables fue exitosa")
    filename: str = Field(..., description="Nombre del archivo original procesado")
    extracted_text: str = Field(..., description="Texto completo extraído del documento")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Variables contractuales estructuradas extraídas (partes, fechas, valor, NIT, etc.)")
    chunks_indexed: int = Field(default=0, description="Cantidad de fragmentos indexados en la Bóveda RAG para búsqueda semántica")
    message: str = Field(..., description="Mensaje de estado informativo")
