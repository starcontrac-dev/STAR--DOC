import logging
import asyncio
import random
import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]

class BaseScraper(ABC):
    """
    Clase abstracta base para los scrapers de fuentes jurídicas colombianas.
    Maneja la lógica de cliente HTTPX asíncrono, User-Agents y reintentos asíncronos robustos.
    """
    
    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection": "keep-alive"
        }

    async def safe_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Realiza una petición GET de forma segura con reintentos asíncronos y backoff exponencial.
        """
        client = await self.get_client()
        headers = self._get_headers()
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Petición GET a {url} (Intento {attempt}/{self.max_retries})")
                res = await client.get(url, params=params, headers=headers)
                
                if res.status_code == 200:
                    return res.text
                elif res.status_code in [403, 429]:
                    # Espera con delay aleatorio más largo si hay bloqueos
                    wait_time = (2 ** attempt) + random.uniform(1.0, 3.0)
                    logger.warning(f"Código {res.status_code} recibido de {url}. Reintentando en {wait_time:.2f}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Error {res.status_code} al acceder a {url}. Reintentando...")
                    await asyncio.sleep(1.0)
                    
            except httpx.RequestError as exc:
                wait_time = (2 ** attempt) + random.uniform(0.5, 1.5)
                logger.error(f"Error de red en intento {attempt} para {url}: {exc}. Reintentando en {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)
                
        logger.error(f"Fallo definitivo al intentar descargar la URL {url} después de {self.max_retries} intentos.")
        return None

    @abstractmethod
    async def scrape(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Método abstracto a implementar por los scrapers específicos.
        Debe retornar una lista de diccionarios con la estructura de chunks.
        """
        pass
