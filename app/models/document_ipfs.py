"""Modelo SQLModel para documentos anclados en IPFS.

Registra cada documento subido a la red IPFS con su CID, hash SHA-256,
estado de pinning, clasificación de seguridad y metadatos de auditoría.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, LargeBinary


class DocumentIPFS(SQLModel, table=True):
    """Registro de documento anclado en IPFS con trazabilidad completa."""
    __tablename__ = "documents_ipfs"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Relaciones opcionales con otras tablas del sistema
    document_id: Optional[int] = Field(default=None, index=True)
    user_id: Optional[int] = Field(default=None, index=True)

    # ── Identificadores IPFS ──
    ipfs_cid: str = Field(index=True, unique=True)
    ipfs_cid_original: Optional[str] = Field(default=None, index=True, nullable=True)
    sha256_original: str = Field(index=True)

    # ── Clasificación y seguridad ──
    classification: str = Field(default="public")  # public | confidential | chain_of_custody
    is_encrypted: bool = Field(default=False)
    encryption_key_encrypted: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )

    # ── Metadatos del archivo original ──
    original_filename: str
    file_size_bytes: int
    mime_type: Optional[str] = None

    # ── Estado de Pinning ──
    pinned_kubo: bool = Field(default=False)
    pinned_pinata: bool = Field(default=False)
    pinata_pin_id: Optional[str] = None

    # ── Blockchain (Fase posterior) ──
    blockchain_tx_hash: Optional[str] = None
    blockchain_network: Optional[str] = None

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    verified_at: Optional[datetime] = None

    # ── URLs de acceso ──
    gateway_url: Optional[str] = None
