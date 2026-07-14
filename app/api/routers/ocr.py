import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_active_user
from app.models.user import User
from app.database import get_session
from app.schemas.ocr import OcrResponse
from app.services.ocr_service import OcrService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ocr", tags=["Legal AI Engine"])

@router.post("/analyze", response_model=OcrResponse, status_code=status.HTTP_200_OK)
async def analyze_document_ocr(
    file: UploadFile = File(..., description="Imagen (PNG, JPEG, WEBP) o PDF escaneado del documento"),
    category: str = Form("OCR", description="Categoría asociada al documento para indexación en RAG"),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Endpoint para realizar OCR Multimodal con Gemini sobre documentos escaneados.
    Extrae el texto completo, estructurando las variables contractuales identificadas,
    e indexa semánticamente los fragmentos en la Bóveda RAG local.
    """
    logger.info(f"Usuario {current_user.email} solicitó OCR para el archivo {file.filename}")

    # Validar tipos MIME soportados por la API multimodal de Gemini
    allowed_mimes = [
        "image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic", "image/heif",
        "application/pdf"
    ]
    
    mime_type = file.content_type
    # Si el content_type es genérico u omitido, intentar inferir o validar por extensión
    if not mime_type or mime_type == "application/octet-stream":
        ext = file.filename.split(".")[-1].lower()
        if ext in ["png"]:
            mime_type = "image/png"
        elif ext in ["jpg", "jpeg"]:
            mime_type = "image/jpeg"
        elif ext in ["webp"]:
            mime_type = "image/webp"
        elif ext in ["pdf"]:
            mime_type = "application/pdf"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Formato de archivo '{ext}' no soportado para OCR Multimodal. Use imágenes o PDFs."
            )

    if mime_type not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de archivo '{mime_type}' no soportado. Debe ser PNG, JPEG, WEBP o PDF."
        )

    try:
        # Leer el contenido del archivo
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo subido está vacío."
            )

        # Ejecutar el servicio de OCR
        response = await OcrService.perform_ocr(
            file_bytes=file_bytes,
            filename=file.filename,
            mime_type=mime_type,
            category=category,
            session=session
        )
        
        if not response.get("success", False):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.get("message", "Error interno procesando OCR.")
            )

        return OcrResponse(
            success=response["success"],
            filename=response["filename"],
            extracted_text=response["extracted_text"],
            variables=response["variables"],
            chunks_indexed=response["chunks_indexed"],
            message=response["message"]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando OCR del archivo {file.filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error inesperado al procesar el OCR del documento: {str(e)}"
        )
