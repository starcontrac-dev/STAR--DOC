"""
Handlers de herramientas de documentos del usuario (Bóveda RAG).

Herramientas:
- list_my_documents: Lista los documentos subidos por el usuario
- read_my_document: Lee el contenido de un documento de la bóveda
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.tools.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool("list_my_documents")
async def handle_list_my_documents(args: dict, session: AsyncSession, username: str) -> dict:
    """Lista los documentos previamente subidos por el usuario a su Bóveda RAG."""
    if username == "Anonimo":
        return {"error": "Usuario no autenticado"}
    try:
        from app.models.user import User
        from app.models.user_document import UserDocument

        user = (await session.execute(
            select(User).where(User.username == username)
        )).scalar_one_or_none()
        if not user:
            return {"error": "Usuario no encontrado"}

        docs = (await session.execute(
            select(UserDocument).where(UserDocument.user_id == user.id)
        )).scalars().all()
        if not docs:
            return {"message": "La bóveda del usuario está vacía. No tiene documentos guardados."}
        
        return {
            "documents": [
                {
                    "document_id": d.id,
                    "filename": d.filename,
                    "upload_date": d.upload_date.isoformat()
                }
                for d in docs
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@register_tool("read_my_document")
async def handle_read_my_document(args: dict, session: AsyncSession, username: str) -> dict:
    """Lee el texto completo de un documento almacenado en la Bóveda RAG del usuario."""
    if username == "Anonimo":
        return {"error": "Usuario no autenticado"}
    
    doc_id = args.get("document_id")
    if not doc_id:
        return {"error": "Falta el ID del documento"}
    
    try:
        from app.models.user import User
        from app.models.user_document import UserDocument

        user = (await session.execute(
            select(User).where(User.username == username)
        )).scalar_one_or_none()
        if not user:
            return {"error": "Usuario no encontrado"}
        
        doc = await session.get(UserDocument, doc_id)
        if not doc or doc.user_id != user.id:
            return {"error": "Documento no encontrado o no pertenece a ti."}
        
        text = doc.content_text
        if len(text) > 100000:
            text = text[:100000] + "\n...[TRUNCADO]"
        return {"document_id": doc_id, "filename": doc.filename, "content": text}
    except Exception as e:
        return {"error": str(e)}


@register_tool("compare_documents")
async def handle_compare_documents(args: dict, session: AsyncSession, username: str) -> dict:
    """Compara dos textos de documentos legales y evalúa los riesgos legales."""
    original_text = args.get("original_text")
    modified_text = args.get("modified_text")
    
    if not original_text or not modified_text:
        return {"error": "Falta el texto original o el modificado para comparar."}
        
    try:
        from app.services.diff_service import DiffService
        html_diff = DiffService.generate_html_diff(original_text, modified_text)
        analysis = await DiffService.analyze_legal_risk_with_gemini(original_text, modified_text)
        
        return {
            "success": True,
            "html_diff": html_diff,
            "analysis": analysis
        }
    except Exception as e:
        logger.error(f"Error en tool compare_documents: {e}")
        return {"error": str(e)}
