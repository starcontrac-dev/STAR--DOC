from typing import Optional, Any
from pgvector.sqlalchemy import Vector
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Index

class LegalKnowledgeChunk(SQLModel, table=True):
    __tablename__ = "legal_knowledge_chunks"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(index=True)  # Ej: 'Constitución Política', 'Ley 1480 de 2011', 'Sentencia SU-070/2013'
    citation: str = Field(index=True)  # Ej: 'Artículo 86', 'Artículo 42'
    content: str  # Texto plano del fragmento
    category: str = Field(index=True)  # Ej: 'constitucional', 'civil', 'comercial', 'consumidor', 'administrativo', 'jurisprudencia'
    
    # Columna Vectorial de 1536 dimensiones para embeddings de Gemini (Matryoshka)
    embedding: Any = Field(sa_column=Column(Vector(1536), nullable=False))

    __table_args__ = (
        Index(
            'hnsw_legal_embedding_idx',
            'embedding',
            postgresql_using='hnsw',
            postgresql_ops={'embedding': 'vector_cosine_ops'},
            postgresql_with={'m': 16, 'ef_construction': 64}
        ),
    )


