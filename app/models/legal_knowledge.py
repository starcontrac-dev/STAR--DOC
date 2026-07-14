from typing import Optional, Any
from pgvector.sqlalchemy import Vector
from sqlmodel import SQLModel, Field
from sqlalchemy import Column

class LegalKnowledgeChunk(SQLModel, table=True):
    __tablename__ = "legal_knowledge_chunks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)  # Ej: 'Constitución Política', 'Ley 1480 de 2011', 'Sentencia SU-070/2013'
    citation: str = Field(index=True)  # Ej: 'Artículo 86', 'Artículo 42'
    content: str  # Texto plano del fragmento
    category: str = Field(index=True)  # Ej: 'constitucional', 'civil', 'comercial', 'consumidor', 'administrativo', 'jurisprudencia'
    
    # Columna Vectorial de 3072 dimensiones para embeddings de Gemini
    embedding: Any = Field(sa_column=Column(Vector(3072), nullable=False))
