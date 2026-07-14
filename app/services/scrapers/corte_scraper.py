import re
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from app.services.scrapers.base_scraper import BaseScraper
from app.services.scrapers.suin_scraper import SUINScraper

logger = logging.getLogger(__name__)

# Fallbacks locales de jurisprudencia colombiana clave (Corte Constitucional)
FALLBACK_JURISPRUDENCIA = [
    {
        "source": "Corte Constitucional - Sentencia SU-070 de 2013",
        "category": "jurisprudencia",
        "citation": "Sentencia SU-070/13 (Estabilidad Laboral de Embarazada)",
        "content": "La Corte Constitucional unifica las reglas sobre el fuero de maternidad y la estabilidad laboral reforzada de las mujeres gestantes y lactantes en los contratos de trabajo. Establece que la protección constitucional se activa desde el momento en que se inicia el estado de embarazo y no depende de la notificación formal al empleador, aunque el conocimiento del embarazo por parte del empleador determina el grado de protección y el alcance de las medidas de reintegro y pago de salarios caídos."
    },
    {
        "source": "Corte Constitucional - Sentencia T-025 de 2004",
        "category": "jurisprudencia",
        "citation": "Sentencia T-025/04 (Estado de Cosas Inconstitucional)",
        "content": "La Corte declara la existencia de un Estado de Cosas Inconstitucional en relación con la situación de la población internamente desplazada en Colombia, debido a la falta de concordancia entre la gravedad de la afectación de los derechos constitucionales de los desplazados y el volumen de recursos efectivamente destinados a su atención y protección. Se ordenan medidas estructurales y presupuestales obligatorias para mitigar la vulneración sistemática de derechos fundamentales."
    },
    {
        "source": "Corte Constitucional - Sentencia C-590 de 2005",
        "category": "jurisprudencia",
        "citation": "Sentencia C-590/05 (Procedencia de tutela contra providencias)",
        "content": "Establece los requisitos generales y específicos de procedibilidad de la acción de tutela contra providencias judiciales. Entre los requisitos generales se encuentran: relevancia constitucional, agotamiento de recursos ordinarios, principio de inmediatez y que no se trate de una tutela contra tutela. Los requisitos específicos (defectos) incluyen el defecto orgánico, defecto procedimental absoluto, defecto fáctico, defecto sustantivo o violación directa de la Constitución."
    },
    {
        "source": "Corte Constitucional - Sentencia T-230 de 2020 (Criptoactivos y Cuentas Bancarias)",
        "category": "jurisprudencia",
        "citation": "Sentencia T-230/20 (Bloqueo financiero a exchanges)",
        "content": "La Sala de Revisión analiza la legalidad del cierre de cuentas bancarias a plataformas que transan con criptoactivos o monedas digitales en Colombia. Concluye que, aunque las entidades financieras gozan de la autonomía de la voluntad privada para contratar, no pueden ejercer un poder de veto arbitrario sin motivación suficiente o vulnerando el debido proceso y la libertad de empresa del usuario, especialmente ante la ausencia de una prohibición legal expresa de los criptoactivos en Colombia."
    }
]

class CorteScraper(BaseScraper):
    """
    Scraper para la Corte Constitucional de Colombia.
    Extrae sentencias y jurisprudencia unificada. Dispone de fallbacks de jurisprudencia
    clave unificada (Sentencias de Tutela y Constitucionalidad) para robustez industrial.
    """

    async def scrape(self, url: Optional[str] = None, category: str = "jurisprudencia") -> List[Dict[str, Any]]:
        """
        Scrapea el HTML de una sentencia de la Corte Constitucional.
        Si la URL es nula o falla la descarga, retorna el fallback de jurisprudencia base colombiana.
        """
        if not url:
            logger.info("No se especificó URL para CorteScraper. Usando jurisprudencia local (fallback).")
            return FALLBACK_JURISPRUDENCIA

        html_content = await self.safe_get(url)
        if not html_content:
            logger.warning("Fallo en la descarga web de la sentencia de la Corte. Usando fallback de jurisprudencia.")
            return FALLBACK_JURISPRUDENCIA

        try:
            return self._parse_html(html_content, url, category)
        except Exception as e:
            logger.error(f"Error parseando sentencia de la Corte: {e}. Usando fallback local.")
            return FALLBACK_JURISPRUDENCIA

    def _parse_html(self, html: str, url: str, category: str) -> List[Dict[str, Any]]:
        """
        Parsea el texto de la sentencia en fragmentos semánticos.
        """
        soup = BeautifulSoup(html, "html.parser")
        
        # Intentar deducir la radicación/número de sentencia desde el título o encabezados
        title_el = soup.find("h1") or soup.find("title") or soup.find(class_="titulo")
        source_name = title_el.text.strip() if title_el else "Sentencia Corte Constitucional"
        source_name = re.sub(r'\s+', ' ', source_name)

        # Buscar el contenedor de texto principal
        content_container = soup.find(id="contenido") or soup.find(class_="content") or soup
        paragraphs = content_container.find_all(["p", "div"])
        
        text_blocks = []
        for p in paragraphs:
            text = p.text.strip()
            # Omitir textos muy cortos o vacíos
            if len(text) > 30:
                # Limpiar saltos
                text = re.sub(r'\s+', ' ', text)
                text_blocks.append(text)
                
        full_text = " ".join(text_blocks)
        
        if not full_text:
            logger.warning("No se logró extraer texto del cuerpo de la sentencia. Usando fallback.")
            return FALLBACK_JURISPRUDENCIA
            
        # Segmentar el texto semánticamente
        chunks = SUINScraper.split_text_semantically(
            text=full_text,
            source=source_name,
            category=category,
            chunk_size=2000,
            overlap=200
        )
        
        logger.info(f"Scraping y chunking completado para {source_name}. Total chunks: {len(chunks)}")
        return chunks
