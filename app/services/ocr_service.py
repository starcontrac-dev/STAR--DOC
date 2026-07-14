import base64
import logging
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_service import AIService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

class OcrService:
    """
    Servicio de OCR Multimodal que utiliza Gemini para extraer texto y variables
    estructuradas de imágenes y PDFs escaneados, e indexa la información en el RAG.
    """

    @staticmethod
    async def perform_ocr(
        file_bytes: bytes,
        filename: str,
        mime_type: str,
        category: str = "OCR",
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Envía una imagen o PDF a la API de Gemini de forma asíncrona para transcribir el texto
        y extraer metadatos del contrato en formato estructurado. Opcionalmente indexa fragmentos en pgvector.
        """
        logger.info(f"Iniciando OCR con Gemini para {filename} ({mime_type})")

        # 1. Codificar bytes en base64
        base64_data = base64.b64encode(file_bytes).decode("utf-8")

        # 2. Configurar el prompt del sistema y de análisis
        prompt = (
            "Analiza detalladamente el documento adjunto (imagen o PDF). "
            "Tu tarea es realizar dos acciones:\n"
            "1. Transcribe fielmente la totalidad del texto legible que encuentres en el documento. "
            "Coloca esta transcripción completa en el campo 'extracted_text'.\n"
            "2. Extrae las variables y metadatos contractuales más importantes que identifiques en el escrito "
            "(como nombres de partes contratantes, NITs/cédulas, fecha del acuerdo, valor del contrato, "
            "objeto del contrato, y obligaciones principales). Estructura estos datos en el campo 'variables'.\n\n"
            "Retorna estrictamente el resultado en formato JSON bajo el siguiente esquema:\n"
            "{\n"
            "  \"extracted_text\": \"Texto completo transcrito...\",\n"
            "  \"variables\": {\n"
            "    \"partes\": [\"Nombre Parte A\", \"Nombre Parte B\"],\n"
            "    \"identificaciones\": [\"Cédula/NIT A\", \"Cédula/NIT B\"],\n"
            "    \"valor\": \"Monto del contrato si aplica\",\n"
            "    \"objeto\": \"Breve descripción del objeto contractual\",\n"
            "    \"fecha\": \"Fecha del documento si está disponible\"\n"
            "  }\n"
            "}"
        )

        # 3. Construir el payload compatible con generateContent de Gemini
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        },
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_data
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json"
            }
        }

        # 4. Enviar a Gemini (por defecto usa gemini-2.5-flash por ser el más eficiente en multimedia)
        ai_service = AIService()
        try:
            raw_response = await ai_service.generate_content(
                payload=payload,
                model="gemini-2.5-flash",
                timeout=60.0
            )

            # Extraer el texto de la respuesta estructurada de Gemini
            candidates = raw_response.get("candidates", [])
            if not candidates:
                raise ValueError("La respuesta de Gemini no contiene candidatos válidos.")

            content_text = candidates[0].get("content", {}).get("parts", [])[0].get("text", "")
            if not content_text:
                raise ValueError("El texto extraído de la API de Gemini está vacío.")

            # Parsear la salida JSON devuelta por la configuración de responseMimeType
            result = json.loads(content_text.strip())
            extracted_text = result.get("extracted_text", "")
            variables = result.get("variables", {})

            # 5. Si se proporciona sesión de base de datos, indexar los datos en el RAG
            chunks_count = 0
            if session is not None and extracted_text:
                logger.info(f"Indexando texto extraído de {filename} en la Bóveda RAG...")
                chunks_count = await OcrService._index_text_in_rag(
                    session=session,
                    filename=filename,
                    text_content=extracted_text,
                    category=category
                )

            return {
                "success": True,
                "filename": filename,
                "extracted_text": extracted_text,
                "variables": variables,
                "chunks_indexed": chunks_count,
                "message": f"Extracción completada. {chunks_count} fragmentos agregados a la Bóveda RAG."
            }

        except Exception as e:
            logger.error(f"Error procesando OCR con Gemini para {filename}: {e}", exc_info=True)
            return {
                "success": False,
                "filename": filename,
                "extracted_text": "",
                "variables": {},
                "chunks_indexed": 0,
                "message": f"Fallo al procesar OCR multimodal: {str(e)}"
            }

    @staticmethod
    async def _index_text_in_rag(
        session: AsyncSession,
        filename: str,
        text_content: str,
        category: str
    ) -> int:
        """
        Divide el texto en chunks y los indexa en la base de datos de pgvector.
        """
        # Limpiar texto de espacios múltiples y normalizar líneas
        clean_text = re.sub(r'\s+', ' ', text_content).strip()
        
        # Dividir en chunks de 1200 caracteres con un solape de 150 caracteres
        chunk_size = 1200
        overlap = 150
        
        chunks = []
        start = 0
        while start < len(clean_text):
            end = min(start + chunk_size, len(clean_text))
            chunk_data = clean_text[start:end]
            chunks.append(chunk_data)
            if end == len(clean_text):
                break
            start += chunk_size - overlap

        # Agregar cada chunk asíncronamente
        added_count = 0
        for i, chunk in enumerate(chunks, 1):
            try:
                citation = f"OCR Pág/Bloque {i}"
                await RAGService.add_chunk(
                    session=session,
                    source=filename,
                    citation=citation,
                    content=chunk,
                    category=category
                )
                added_count += 1
            except Exception as ex:
                logger.error(f"Error guardando chunk RAG {i} de {filename}: {ex}")
                
        return added_count
