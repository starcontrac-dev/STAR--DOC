import logging
import io
from fastapi import UploadFile
import fitz  # PyMuPDF
import docx

logger = logging.getLogger(__name__)

async def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """
    Extracts text from bytes content based on filename extension.
    Supports: .pdf, .docx, .txt, .md
    """
    filename = filename.lower()
    
    try:
        if filename.endswith(".pdf"):
            return _extract_pdf(content)
        elif filename.endswith(".docx"):
            return _extract_docx(content)
        elif filename.endswith((".txt", ".md")):
            return _extract_text(content)
        else:
            # Fallback
            return _extract_text(content)
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        return f"[Error al leer el archivo {filename}: {str(e)}]"

async def extract_text_from_file(file: UploadFile) -> str:
    content = await file.read()
    await file.seek(0)
    return await extract_text_from_bytes(content, file.filename)

def _extract_pdf(content: bytes) -> str:
    """Extracts text from PDF bytes using PyMuPDF (fitz) for reliable table and block parsing."""
    try:
        doc = fitz.open("pdf", content)
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        return text.strip()
    except Exception as e:
        logger.error(f"Error parsing PDF with PyMuPDF: {e}")
        raise ValueError(f"Could not parse PDF: {e}")

def _extract_docx(content: bytes) -> str:
    """Extracts text from DOCX bytes using python-docx."""
    try:
        doc = docx.Document(io.BytesIO(content))
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        raise ValueError(f"Could not parse DOCX: {e}")

def _extract_text(content: bytes) -> str:
    """Decodes bytes to string assuming UTF-8 or Latin-1."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")
        except Exception as e:
            raise ValueError(f"Could not decode text: {e}")
