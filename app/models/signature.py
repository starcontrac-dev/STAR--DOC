"""
Modelo de base de datos SQLModel para solicitudes de firma electrónica digital.
"""
from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship

class SignatureRequest(SQLModel, table=True):
    """
    Rastrea solicitudes de firma electrónica conformes con la Ley 527 de 1999 de Colombia.
    """
    __tablename__ = "signature_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Abogado que solicita la firma
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # Nombre del archivo físico ubicado en settings.OUTPUT_DIR (usualmente PDF)
    document_filename: str = Field(index=True)
    
    # Estado global: pending | in_progress | completed | expired
    status: str = Field(default="pending", index=True)
    
    # Clasificación de privacidad: public | confidential | chain_of_custody
    classification: str = Field(default="chain_of_custody", max_length=50, index=True)
    
    # Relación uno a muchos con la nueva tabla de firmantes (normalizada)
    signers: List["SignatureSigner"] = Relationship(
        back_populates="request", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"}
    )
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expiration: datetime = Field(index=True)
    
    # CID de IPFS del documento firmado consolidado
    signed_document_cid: Optional[str] = Field(default=None, index=True)
    
    # Hash SHA-256 de integridad del documento firmado final
    sha256_signed: Optional[str] = Field(default=None, index=True)


class SignatureSigner(SQLModel, table=True):
    """
    Representa a cada uno de los firmantes de un documento de forma normalizada.
    Cumple con el principio de autenticidad e integridad del Decreto 2364 de 2012.
    """
    __tablename__ = "signature_signers"

    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Clave foránea al documento padre
    signature_request_id: int = Field(foreign_key="signature_requests.id", index=True)
    
    name: str = Field(max_length=255)
    email: str = Field(max_length=255, index=True)
    signed: bool = Field(default=False)
    signed_at: Optional[datetime] = Field(default=None)
    ip: Optional[str] = Field(default=None, max_length=45)
    user_agent: Optional[str] = Field(default=None)
    
    # Token único de acceso a firma (UUIDv4) para búsquedas indexadas directas en O(1)
    token: str = Field(unique=True, index=True)
    
    # Firma caligráfica en Base64 cifrada temporalmente (se purga a None al finalizar la consolidación)
    signature_image_encrypted: Optional[str] = Field(default=None)
    
    # Código OTP para doble factor de autenticación (2FA) por correo
    otp_code: Optional[str] = Field(default=None, max_length=6)
    otp_expires_at: Optional[datetime] = Field(default=None)
    
    # Consentimientos de Ley
    consent_electronic_signature: bool = Field(default=False)
    consent_habeas_data: bool = Field(default=False)
    
    # Evidencias de video-consentimiento (antes anidadas en JSON)
    video_rec_cid: Optional[str] = Field(default=None, max_length=100)
    video_sha256: Optional[str] = Field(default=None, max_length=64)
    declaration_text: Optional[str] = Field(default=None)
    
    # Relación inversa
    request: SignatureRequest = Relationship(
        back_populates="signers",
        sa_relationship_kwargs={"lazy": "selectin"}
    )
