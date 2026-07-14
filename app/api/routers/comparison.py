"""
Router de API para la comparación inteligente de documentos en STAR-DOC.
"""
import os
import shutil
import tempfile
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.auth import get_current_active_user
from app.models.user import User
from app.services.diff_service import DiffService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comparison", tags=["Document Comparison"])

@router.post("/compare-documents")
async def compare_documents(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user)
):
    """
    Compara dos archivos (.md, .docx o .pdf) y genera:
    1. Un diff visual HTML estilizado.
    2. Un análisis semántico de riesgo legal con Gemini API.
    """
    logger.info(f"Usuario {current_user.email} solicitó comparación: '{file_a.filename}' vs '{file_b.filename}'")
    
    # Validar extensiones soportadas
    allowed_exts = {".md", ".docx", ".pdf", ".txt"}
    ext_a = os.path.splitext(file_a.filename)[1].lower()
    ext_b = os.path.splitext(file_b.filename)[1].lower()
    
    if ext_a not in allowed_exts or ext_b not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail="Formato de archivo no soportado. Suba archivos .md, .txt, .docx o .pdf"
        )
        
    # Guardar archivos en directorio temporal para procesarlos
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path_a = os.path.join(temp_dir, f"file_a{ext_a}")
        temp_path_b = os.path.join(temp_dir, f"file_b{ext_b}")
        
        try:
            with open(temp_path_a, "wb") as buffer_a:
                shutil.copyfileobj(file_a.file, buffer_a)
                
            with open(temp_path_b, "wb") as buffer_b:
                shutil.copyfileobj(file_b.file, buffer_b)
        except Exception as e:
            logger.error(f"Error guardando temporales: {e}")
            raise HTTPException(status_code=500, detail="Error de almacenamiento temporal de archivos.")
            
        # Extraer texto de ambos archivos
        try:
            text_a = DiffService.extract_text(temp_path_a)
            text_b = DiffService.extract_text(temp_path_b)
        except Exception as e:
            logger.error(f"Error extrayendo texto: {e}")
            raise HTTPException(status_code=422, detail=f"Error al extraer texto: {str(e)}")
            
        # Validar contenido mínimo
        if not text_a.strip() or not text_b.strip():
            raise HTTPException(
                status_code=400,
                detail="Uno o ambos archivos no contienen texto legible para procesar."
            )
            
        # Generar diff visual e invocar Gemini para análisis de riesgos
        try:
            html_diff = DiffService.generate_html_diff(text_a, text_b)
            legal_analysis = await DiffService.analyze_legal_risk_with_gemini(text_a, text_b)
            
            return {
                "success": True,
                "filenames": {
                    "original": file_a.filename,
                    "modified": file_b.filename
                },
                "html_diff": html_diff,
                "analysis": legal_analysis
            }
        except Exception as e:
            logger.error(f"Error procesando diff/análisis Gemini: {e}")
            raise HTTPException(status_code=500, detail=f"Error durante el análisis del documento: {str(e)}")
