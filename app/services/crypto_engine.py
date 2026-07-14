"""Motor de encriptación AES-256-GCM para documentos legales."""
import os
import hashlib
import base64
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from enum import Enum
from app.core.config import settings

class DocClassification(str, Enum):
    """Clasificación de seguridad documental."""
    PUBLIC = "public"           # Sin encriptación
    CONFIDENTIAL = "confidential"  # Encriptado
    CHAIN_OF_CUSTODY = "chain_of_custody"  # Encriptado + audit trail

class CryptoEngine:
    """Encriptación AES-256-GCM de grado legal."""

    NONCE_SIZE = 12  # 96 bits según NIST SP 800-38D

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Calcula el hash SHA-256 del documento original."""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def encrypt(data: bytes) -> tuple[bytes, bytes, bytes]:
        """
        Encripta datos con AES-256-GCM.
        Retorna: (datos_encriptados, llave, nonce)
        """
        key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(CryptoEngine.NONCE_SIZE)
        aesgcm = AESGCM(key)
        # GCM incluye tag de autenticación automáticamente
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return ciphertext, key, nonce

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
        """Desencripta y verifica integridad (GCM auth tag)."""
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    @staticmethod
    def encrypt_with_envelope(data: bytes, key: Optional[bytes] = None) -> dict:
        """
        Encripta y retorna un sobre completo con metadatos.
        El nonce se prepende al ciphertext para simplificar almacenamiento.
        """
        sha256_original = CryptoEngine.compute_sha256(data)
        if key is None:
            key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(CryptoEngine.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        # Prepender nonce al ciphertext para almacenamiento único
        envelope_data = nonce + ciphertext
        return {
            "encrypted_data": envelope_data,
            "encryption_key": key,
            "sha256_original": sha256_original,
            "original_size": len(data),
            "algorithm": "AES-256-GCM",
            "nonce_size": CryptoEngine.NONCE_SIZE,
        }

    @staticmethod
    def decrypt_from_envelope(envelope_data: bytes, key: bytes) -> bytes:
        """Desencripta desde el formato de sobre (nonce + ciphertext)."""
        nonce = envelope_data[:CryptoEngine.NONCE_SIZE]
        ciphertext = envelope_data[CryptoEngine.NONCE_SIZE:]
        return CryptoEngine.decrypt(ciphertext, key, nonce)

    @staticmethod
    def get_master_key_for_user(user_id: Optional[int]) -> bytes:
        """
        Deriva una clave maestra simétrica a partir de settings.SECRET_KEY y del user_id.
        Si el user_id es None o 0, usa un fallback consistente (0).
        Utiliza PBKDF2 para generar una clave de 256 bits codificada en base64 url-safe (para Fernet).
        """
        uid = user_id if user_id is not None else 0
        salt = f"star-doc-envelope-salt-{uid}".encode("utf-8")
        key_material = hashlib.pbkdf2_hmac(
            "sha256",
            settings.SECRET_KEY.encode("utf-8"),
            salt,
            iterations=100000,
            dklen=32
        )
        return base64.urlsafe_b64encode(key_material)

    @staticmethod
    def encrypt_document_key(key: bytes, user_id: Optional[int]) -> bytes:
        """
        Cifra la llave simétrica del documento usando una clave maestra derivada del user_id.
        """
        from cryptography.fernet import Fernet
        master_key = CryptoEngine.get_master_key_for_user(user_id)
        f = Fernet(master_key)
        return f.encrypt(key)

    @staticmethod
    def decrypt_document_key(encrypted_key: bytes, user_id: Optional[int]) -> bytes:
        """
        Desencripta la llave simétrica del documento usando la clave maestra derivada del user_id.
        Soporta fallback por si la llave estaba almacenada sin cifrar (legacy).
        """
        from cryptography.fernet import Fernet
        from cryptography.fernet import InvalidToken
        
        try:
            master_key = CryptoEngine.get_master_key_for_user(user_id)
            f = Fernet(master_key)
            return f.decrypt(encrypted_key)
        except (InvalidToken, ValueError, TypeError):
            # Si falla, asumimos que es una llave legacy almacenada sin cifrar.
            return encrypted_key
