import httpx
import logging
from typing import Any, Dict, Optional
import random
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1"
]

class StandardHTTPClient:
    """
    Cliente HTTP asíncrono con funcionalidades para scraping y APIs que requieren evasión básica 
    o tolerancia a fallos.
    Implementa patrón Singleton para habilitar Connection Pooling global.
    Utiliza Tenacity para gestionar los reintentos de forma profesional y resiliente.
    """
    _instance = None
    _client: Optional[httpx.AsyncClient] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(StandardHTTPClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, timeout: int = 15, max_retries: int = 3):
        # Prevenimos reinicializar al instanciar múltiples veces
        if not hasattr(self, '_initialized'):
            self.timeout = timeout
            self.max_retries = max_retries
            self._initialized = True

    @property
    def client(self) -> httpx.AsyncClient:
        # Inicialización lazy. Solo se crea el cliente cuando el Event Loop está activo
        if self._client is None or self._client.is_closed:
            # Habilitamos http2 para máximo rendimiento
            self._client = httpx.AsyncClient(timeout=self.timeout, http2=True)
        return self._client

    async def close(self):
        """Cierra explícitamente las conexiones activas si se requiere."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_headers(self, custom_headers: Optional[Dict] = None) -> Dict:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-CO,es;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if custom_headers:
            headers.update(custom_headers)
        return headers

    async def get(self, url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None) -> httpx.Response:
        return await self._request("GET", url, params=params, headers=headers)

    async def post(self, url: str, data: Any = None, json_data: Any = None, headers: Optional[Dict] = None) -> httpx.Response:
        return await self._request("POST", url, data=data, json_data=json_data, headers=headers)

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        kwargs["headers"] = self._get_headers(kwargs.get("headers"))
        
        # Tenacity retry-loop encapsulado utilizando los valores de la clase
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=10),
            stop=stop_after_attempt(self.max_retries),
            reraise=True  # Relanza la última excepción que causó el fallo
        )
        async def do_request():
            try:
                if method == "GET":
                    response = await self.client.get(url, params=kwargs.get("params"), headers=kwargs["headers"])
                else:
                    response = await self.client.post(url, data=kwargs.get("data"), json=kwargs.get("json_data"), headers=kwargs["headers"])
                
                response.raise_for_status()
                return response
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"Fallo en {url} con status {e.response.status_code}")
                # No reintentar si el error es del cliente (4xx) ya que no se solucionará volviendo a consultar
                if 400 <= e.response.status_code < 500:
                    raise e
                # Es 5xx, lanzamos la excepción limpia para que Tenacity la recoja y reintente
                raise Exception(f"HTTP Server Error: {e.response.status_code}") from e
                
            except (httpx.RequestError, asyncio.TimeoutError) as e:
                logger.warning(f"Error de red/timeout en {url}: {str(e)}. Reintentando...")
                raise e

        # Executing the Tenacity wrapped function
        return await do_request()
