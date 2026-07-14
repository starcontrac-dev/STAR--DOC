import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

# Fallbacks locales de alta fidelidad si el sitio del gobierno colombiano (SUIN) no responde
FALLBACK_NORMAS = [
    {
        "source": "Constitución Política de Colombia (1991)",
        "category": "constitucional",
        "citation": "Artículo 86 (Acción de Tutela)",
        "content": "Toda persona tendrá acción de tutela para reclamar ante los jueces, en todo momento y lugar, mediante un procedimiento preferente y sumario, por sí misma o por quien actúe a su nombre, la protección inmediata de sus derechos constitucionales fundamentales, cuando quiera que éstos resulten vulnerados o amenazados por la acción o la omisión de cualquiera autoridad pública. La protección consistirá en una orden para que aquel respecto de quien se solicita la tutela, actúe o se abstenga de hacerlo. El fallo, que será de inmediato cumplimiento, podrá impugnarse ante el juez competente y, en todo caso, este lo remitirá a la Corte Constitucional para su eventual revisión."
    },
    {
        "source": "Código de Comercio de Colombia (Decreto 410 de 1971)",
        "category": "comercial",
        "citation": "Artículo 824 (Formalidades contractuales)",
        "content": "Los comerciantes podrán expresar su voluntad de contratar y obligarse verbalmente, por escrito o por cualquier otro medio inequívoco. Cuando una ley exija determinada solemnidad como requisito de existencia o de validez del contrato, como la escritura pública o el documento privado firmado, el acuerdo no se perfeccionará sin dicha formalidad."
    },
    {
        "source": "Ley 1258 de 2008 (Sociedades por Acciones Simplificadas - S.A.S.)",
        "category": "comercial",
        "citation": "Artículo 1 (Constitución de la S.A.S.)",
        "content": "La sociedad por acciones simplificada podrá constituirse por una o varias personas naturales o jurídicas, quienes sólo serán responsables hasta el monto de sus respectivos aportes. Salvo lo previsto en el artículo 42 de la presente ley, el o los accionistas no serán responsables por las obligaciones sociales, tributarias, laborales o de cualquier otra naturaleza en que incurra la sociedad."
    },
    {
        "source": "Ley 1480 de 2011 (Estatuto del Consumidor)",
        "category": "consumidor",
        "citation": "Artículo 47 (Derecho de Retracto)",
        "content": "En todos los contratos para la venta de bienes y prestación de servicios mediante sistemas de financiación otorgada por el productor o proveedor, venta de tiempos compartidos o ventas que utilizan métodos no tradicionales o a distancia, que por su naturaleza no deban consumirse o no hayan comenzado a ejecutarse antes de cinco (5) días, se entenderá pactado el derecho de retracto por parte del consumidor. En el evento en que se haga uso de la facultad de retracto, se resolverá el contrato y se deberá reintegrar el dinero que el consumidor hubiese pagado. El término máximo para ejercer el derecho de retracto será de cinco (5) días hábiles contados a partir de la entrega del bien o de la celebración del contrato en caso de la prestación de servicios."
    },
    {
        "source": "Ley 527 de 1999 (Comercio Electrónico y Firmas Digitales)",
        "category": "comercial",
        "citation": "Artículo 7 (Firma electrónica)",
        "content": "Cuando la ley requiera la firma de una persona, ese requisito quedará satisfecho en relación con un mensaje de datos si se utiliza un método que permita identificar a la persona y para indicar que aprueba la información contenida en el mensaje de datos, y que dicho método sea confiable y apropiado para el propósito por el cual se generó o comunicó el mensaje de datos."
    }
]

class SUINScraper(BaseScraper):
    """
    Scraper para SUIN-Juriscol (Sistema Único de Información Normativa de Colombia).
    Extrae leyes, decretos y códigos. Implementa un fallback local de normas clave
    para robustez industrial en entornos sin conexión o bajo bloqueos de IP del gobierno.
    """

    async def scrape(self, url: Optional[str] = None, category: str = "comercial") -> List[Dict[str, Any]]:
        """
        Scrapea el HTML de una norma en SUIN-Juriscol.
        Si la URL es nula o falla la descarga, retorna el fallback de normas base colombianas.
        """
        if not url:
            logger.info("No se especificó URL para SUINScraper. Usando base de conocimiento local (fallback).")
            return FALLBACK_NORMAS

        html_content = await self.safe_get(url)
        if not html_content:
            logger.warning("Fallo en la descarga web de SUIN. Usando fallback de normas de alta fidelidad.")
            return FALLBACK_NORMAS

        try:
            return self._parse_html(html_content, url, category)
        except Exception as e:
            logger.error(f"Error parseando el HTML de SUIN: {e}. Usando fallback local.")
            return FALLBACK_NORMAS

    def _parse_html(self, html: str, url: str, category: str) -> List[Dict[str, Any]]:
        """
        Parsea el HTML de la norma e identifica artículos.
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Intentar extraer el título de la norma
        title_el = soup.find("h1") or soup.find("title")
        source_name = title_el.text.strip() if title_el else "Norma SUIN-Juriscol"
        # Limpiar espacios
        source_name = re.sub(r'\s+', ' ', source_name)
        
        chunks = []
        current_article = ""
        current_text_blocks = []
        
        # Buscar todos los elementos de párrafo que puedan contener el texto
        # En SUIN-Juriscol los artículos se suelen etiquetar con clases o textos específicos 'Artículo X'
        paragraphs = soup.find_all(["p", "div", "span"])
        
        for p in paragraphs:
            text = p.text.strip()
            if not text:
                continue
                
            # Identificar patrón de inicio de artículo
            art_match = re.match(r'^(ART[IÍ]CULO\s+\d+[\s\.\:\-]|[A-Z][a-z]+\s+\d+[\s\.\:\-])', text, re.IGNORECASE)
            
            if art_match:
                # Si ya teníamos un artículo acumulado, guardarlo
                if current_article and current_text_blocks:
                    chunks.append({
                        "source": source_name,
                        "category": category,
                        "citation": current_article,
                        "content": " ".join(current_text_blocks)
                    })
                current_article = art_match.group(0).strip(".:- ")
                current_text_blocks = [text]
            else:
                if current_article:
                    current_text_blocks.append(text)
                    
        # Guardar el último artículo
        if current_article and current_text_blocks:
            chunks.append({
                "source": source_name,
                "category": category,
                "citation": current_article,
                "content": " ".join(current_text_blocks)
            })

        # Si no se identificó una estructura de artículos limpia (por malformación del HTML),
        # aplicar segmentación por longitud/bloques del texto completo.
        if not chunks:
            full_text = " ".join([p.text.strip() for p in paragraphs if p.text.strip()])
            chunks = self.split_text_semantically(full_text, source_name, category)
            
        logger.info(f"Scraping completado para {source_name}. Total chunks: {len(chunks)}")
        return chunks

    @staticmethod
    def split_text_semantically(text: str, source: str, category: str, chunk_size: int = 2000, overlap: int = 200) -> List[Dict[str, Any]]:
        """
        Segmenta un bloque largo de texto en fragmentos (chunks) más pequeños de forma inteligente
        manteniendo la coherencia semántica mediante solapamiento.
        """
        # Limpiar texto de espacios y saltos múltiples
        cleaned_text = re.sub(r'\s+', ' ', text).strip()
        
        chunks = []
        start = 0
        total_len = len(cleaned_text)
        
        if total_len <= chunk_size:
            return [{
                "source": source,
                "category": category,
                "citation": "Texto Completo",
                "content": cleaned_text
            }]
            
        while start < total_len:
            end = start + chunk_size
            
            # Ajustar el end al final de una oración o párrafo si es posible
            if end < total_len:
                # Buscar punto y seguido más cercano dentro de los últimos 150 caracteres del chunk
                limit = max(start, end - 150)
                punctuation_idx = -1
                for char in ['. ', '; ', '\n']:
                    idx = cleaned_text.rfind(char, limit, end)
                    if idx > punctuation_idx:
                        punctuation_idx = idx
                
                if punctuation_idx != -1:
                    end = punctuation_idx + 1  # Incluye el punto
                    
            chunk_content = cleaned_text[start:end].strip()
            
            # Generar citación aproximada basada en el avance
            progression_percent = int((start / total_len) * 100)
            citation = f"Sección (Progreso ~{progression_percent}%)"
            
            chunks.append({
                "source": source,
                "category": category,
                "citation": citation,
                "content": chunk_content
            })
            
            start = end - overlap
            if start < 0:
                start = end
                
        return chunks
