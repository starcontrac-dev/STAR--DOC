"""
Servicio para la solicitud y gestión de Sellos de Tiempo Criptográficos (Timestamping) bajo el estándar RFC 3161.
Cumple con la legislación colombiana (Ley 527 de 1999) para el no repudio documental.
"""
import os
import logging
import httpx
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

# Estructura binaria ASN.1 DER fija para un TimestampRequest (RFC 3161) con algoritmo SHA-256 y certReq=True.
# Secuencia de 57 bytes (0x39)
TS_REQUEST_HEADER = bytes.fromhex("30 39 02 01 01 30 31 30 0d 06 09 60 86 48 01 65 03 04 02 01 05 00 04 20")
# certReq = True (BOOLEAN, length 1, value 0xFF)
TS_REQUEST_FOOTER = bytes.fromhex("01 01 ff")

class TimestampService:
    @staticmethod
    def build_rfc3161_request(sha256_hex: str) -> bytes:
        """
        Construye la solicitud binaria DER para sellado de tiempo a partir de un hash SHA-256.
        """
        try:
            hash_bytes = bytes.fromhex(sha256_hex)
            if len(hash_bytes) != 32:
                raise ValueError("El hash SHA-256 debe tener exactamente 32 bytes.")
            return TS_REQUEST_HEADER + hash_bytes + TS_REQUEST_FOOTER
        except Exception as e:
            logger.error(f"Error construyendo solicitud RFC 3161: {e}")
            raise

    @staticmethod
    async def request_timestamp_token(
        sha256_hex: str, 
        tsa_url: str = "http://timestamp.digicert.com"
    ) -> Optional[bytes]:
        """
        Envía una solicitud de sellado de tiempo de forma asíncrona a la TSA especificada
        y retorna los bytes del TimeStampToken recibidos (codificación DER).
        """
        logger.info(f"Solicitando sello de tiempo a {tsa_url} para hash: {sha256_hex}")
        try:
            request_data = TimestampService.build_rfc3161_request(sha256_hex)
            headers = {"Content-Type": "application/timestamp-query"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    tsa_url, 
                    content=request_data, 
                    headers=headers, 
                    timeout=15.0
                )
                
                if response.status_code == 200:
                    logger.info("Sello de tiempo recibido exitosamente de la TSA.")
                    return response.content
                else:
                    logger.error(f"El servidor TSA devolvió código de error: {response.status_code}. Respuesta: {response.text[:200]}")
                    return None
        except Exception as e:
            logger.error(f"Excepción al solicitar sello de tiempo de la TSA: {e}", exc_info=True)
            return None

    @staticmethod
    async def stamp_file(
        file_path: str,
        tsa_url: str = "http://timestamp.digicert.com"
    ) -> Optional[str]:
        """
        Calcula el hash de un archivo local, solicita el token de sello de tiempo
        y lo guarda como un archivo adjunto independiente con extensión `.tsr` en el mismo directorio.
        Retorna la ruta absoluta del archivo .tsr generado o None si falla.
        """
        if not os.path.exists(file_path):
            logger.error(f"No se puede estampar: El archivo {file_path} no existe.")
            return None
            
        try:
            # 1. Calcular el Hash SHA-256 del archivo
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            sha256_hex = hasher.hexdigest()
            
            # 2. Solicitar el token de sello de tiempo
            ts_token_bytes = await TimestampService.request_timestamp_token(sha256_hex, tsa_url)
            if not ts_token_bytes:
                # Intento de fallback con Sectigo si Digicert falla
                fallback_tsa = "http://timestamp.sectigo.com"
                logger.info(f"Reintentando con servidor de respaldo de Sectigo: {fallback_tsa}")
                ts_token_bytes = await TimestampService.request_timestamp_token(sha256_hex, fallback_tsa)
                
            if not ts_token_bytes:
                logger.error("No se pudo obtener el sello de tiempo de ningún servidor TSA.")
                return None
                
            # 3. Guardar el archivo .tsr
            tsr_path = f"{file_path}.tsr"
            with open(tsr_path, "wb") as f:
                f.write(ts_token_bytes)
                
            logger.info(f"Sello de tiempo registrado e inyectado en el disco: {tsr_path}")
            return tsr_path
        except Exception as e:
            logger.error(f"Error estampando sello de tiempo al archivo: {e}", exc_info=True)
            return None
