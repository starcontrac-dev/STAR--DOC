"""
Motor Playwright Singleton para scraping de portales judiciales colombianos.

Patrón: Singleton async con contextos aislados y anti-detección.
Uso: scraping de SPAs judiciales (Vue.js, ASP.NET) que requieren JavaScript.

Consideraciones legales:
- Los portales judiciales colombianos contienen datos PÚBLICOS (Art. 228 CN)
- Se implementa rate limiting para no saturar servidores estatales
- Cache temporal (1 hora) para minimizar peticiones
- NO se realiza bypass de captcha
"""

import asyncio
import logging
import random
import threading
import sys
import functools
import os
from typing import Optional, List, Dict

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# Definición de recursos a bloquear para optimización y evasión
RECURSOS_BLOQUEADOS = {
    "image", "media", "font", "other"
}

DOMINIOS_RUTAS_BLOQUEADAS = [
    "google-analytics.com", "googletagmanager.com", "mixpanel.com", 
    "facebook.net", "sentry.io", "hotjar.com"
]

class PlaywrightThreadRunner:
    """
    Runner para aislar Playwright en un hilo dedicado con un ProactorEventLoop.
    Soluciona el NotImplementedError de subprocess_exec en Windows cuando
    Uvicorn fuerza el SelectorEventLoop.
    """
    def __init__(self):
        self.loop = None
        self.thread = None
        self.ready_event = threading.Event()
        
    def _run_loop(self):
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.ready_event.set()
        self.loop.run_forever()
        
    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run_loop, daemon=True, name="PlaywrightThread")
            self.thread.start()
            self.ready_event.wait()

    async def execute(self, coro_func, *args, **kwargs):
        self.start()
        
        async def _wrapper():
            return await coro_func(*args, **kwargs)
            
        future = asyncio.run_coroutine_threadsafe(_wrapper(), self.loop)
        return await asyncio.wrap_future(future)

playwright_thread_runner = PlaywrightThreadRunner()

def run_in_playwright_thread(func):
    """
    Decorador para envolver métodos de búsqueda públicos y ejecutarlos 
    completamente dentro del hilo dedicado de Playwright.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await playwright_thread_runner.execute(func, *args, **kwargs)
    return wrapper

# Agentes de usuario realistas para rotación
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


class RateLimiter:
    """Limitador de velocidad para peticiones a portales gubernamentales.
    
    Mínimo 3 segundos entre peticiones para respetar los servidores estatales.
    """
    def __init__(self, delay: float = 3.0):
        self._lock = asyncio.Lock()
        self._delay = delay

    async def wait(self):
        """Espera el delay mínimo entre peticiones."""
        async with self._lock:
            await asyncio.sleep(self._delay)


# Limitador global: mínimo 3s entre peticiones a portales gov
rate_limiter = RateLimiter(delay=3.0)


class PlaywrightEngine:
    """
    Motor Playwright singleton para scraping de portales judiciales.
    
    Características:
    - Inicialización lazy (no consume memoria hasta que se usa)
    - Contextos aislados (cookies/cache independientes por consulta)
    - Anti-detección con playwright-stealth
    - Rotación de User-Agent
    - Rate limiting integrado
    """
    _instance = None
    _browser: Optional[Browser] = None
    _playwright = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def _ensure_browser(self) -> Browser:
        """Inicialización lazy del navegador Chromium headless."""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-extensions",
                        "--disable-gpu",
                    ]
                )
                logger.info("🎭 Navegador Playwright iniciado (headless Chromium)")
        return self._browser

    def _obtener_configuracion_proxy(self) -> Optional[Dict[str, str]]:
        """Extrae la configuración del proxy de variables de entorno si está disponible."""
        proxy_server = os.getenv("PLAYWRIGHT_PROXY_SERVER")
        if not proxy_server:
            return None
            
        proxy_config = {"server": proxy_server}
        username = os.getenv("PLAYWRIGHT_PROXY_USERNAME")
        password = os.getenv("PLAYWRIGHT_PROXY_PASSWORD")
        
        if username and password:
            proxy_config["username"] = username
            proxy_config["password"] = password
            
        return proxy_config

    async def create_context(self, bloquear_css: bool = False) -> BrowserContext:
        """Crea un contexto de navegador aislado con soporte de proxies y bloqueo avanzado de recursos."""
        browser = await self._ensure_browser()
        proxy_config = self._obtener_configuracion_proxy()
        
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(USER_AGENTS),
            locale="es-CO",
            timezone_id="America/Bogota",
            ignore_https_errors=True,
            proxy=proxy_config  # Inyección dinámica del proxy
        )
        
        # Intercepción de recursos avanzada
        async def interceptar_rutas(route):
            request = route.request
            resource_type = request.resource_type
            url = request.url.lower()
            
            # Bloquear por tipo de recurso
            if resource_type in RECURSOS_BLOQUEADOS:
                await route.abort()
                return
                
            if bloquear_css and resource_type == "stylesheet":
                await route.abort()
                return
                
            # Bloquear dominios de analíticas o rastreo
            if any(dom in url for dom in DOMINIOS_RUTAS_BLOQUEADAS):
                await route.abort()
                return
                
            await route.continue_()

        await context.route("**/*", interceptar_rutas)
        return context

    async def create_stealth_page(self, context: BrowserContext) -> Page:
        """Crea una página con stealth anti-bot y evasión avanzada de fingerprints."""
        page = await context.new_page()
        
        # Ocultación manual de automatización en el motor (evade detección de CDP/WebDriver)
        await page.add_init_script("""
            const newProto = Object.getPrototypeOf(navigator);
            delete newProto.webdriver;
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });

            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });

            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel(R) Iris(R) Xe Graphics';
                return getParameter.apply(this, arguments);
            };
        """)
        
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            logger.debug("🥷 Stealth v2 y scripts de evasión avanzada aplicados a la página")
        except ImportError:
            logger.warning("⚠️ playwright-stealth no instalado, continuando solo con scripts de evasión avanzada")
        except Exception as e:
            logger.warning(f"⚠️ Error aplicando stealth: {e}")
        return page

    @staticmethod
    async def type_like_human(page: Page, selector: str, text: str):
        """Simula tipeo humano con retraso aleatorio por tecla en campos de formulario."""
        await page.wait_for_selector(selector, state="visible", timeout=15000)
        element = page.locator(selector).first
        await element.click()
        await element.clear()
        
        for char in text:
            await element.press(char)
            # Retraso pseudo-aleatorio entre 60 y 160 milisegundos
            await asyncio.sleep(random.uniform(0.06, 0.16))

    async def scrape_page(self, url: str, wait_selector: str,
                          timeout: int = 30000) -> str:
        """
        Navega a URL, espera selector visible y extrae texto.
        
        Args:
            url: URL del portal a navegar
            wait_selector: Selector CSS del elemento a esperar
            timeout: Timeout en milisegundos
            
        Returns:
            Texto del elemento seleccionado
        """
        # Respetar rate limiting
        await rate_limiter.wait()
        
        context = await self.create_context()
        page = await self.create_stealth_page(context)
        try:
            logger.info(f"🌐 Navegando a: {url}")
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            await page.wait_for_selector(wait_selector, state="visible", timeout=timeout)
            text = await page.locator(wait_selector).text_content() or ""
            logger.info(f"✅ Texto extraído ({len(text)} caracteres)")
            return text
        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {e}")
            raise
        finally:
            await page.close()
            await context.close()

    async def scrape_with_interaction(self, url: str, actions: list,
                                       result_selector: str,
                                       timeout: int = 45000) -> str:
        """
        Navega, ejecuta acciones (fill, click) y extrae resultado.
        
        Args:
            url: URL del portal
            actions: Lista de acciones [{"type": "fill"|"click", "selector": "...", "value": "..."}]
            result_selector: Selector del elemento con resultados
            timeout: Timeout en ms
            
        Returns:
            HTML interno del elemento de resultados
        """
        await rate_limiter.wait()
        
        context = await self.create_context()
        page = await self.create_stealth_page(context)
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout)
            
            for action in actions:
                action_type = action.get("type")
                selector = action.get("selector")
                
                if action_type in ("fill", "type_human"):
                    await page.wait_for_selector(selector, state="visible", timeout=15000)
                    await self.type_like_human(page, selector, action.get("value", ""))
                elif action_type == "click":
                    await page.wait_for_selector(selector, state="visible", timeout=15000)
                    await page.locator(selector).first.click()
                elif action_type == "wait":
                    await asyncio.sleep(action.get("seconds", 2))
                    
            # Esperar resultados
            await page.wait_for_selector(result_selector, state="visible", timeout=timeout)
            return await page.locator(result_selector).first.inner_html() or ""
            
        except Exception as e:
            logger.error(f"❌ Error en interacción con {url}: {e}")
            raise
        finally:
            await page.close()
            await context.close()

    async def extract_table_data(self, page: Page, table_selector: str) -> List[Dict]:
        """
        Extrae datos de una tabla HTML en formato estructurado.
        
        Args:
            page: Página Playwright activa
            table_selector: Selector CSS de la tabla
            
        Returns:
            Lista de diccionarios con los datos de cada fila
        """
        rows = await page.locator(f"{table_selector} tbody tr").all()
        # Obtener encabezados
        headers = []
        header_cells = await page.locator(f"{table_selector} thead th").all()
        for hc in header_cells:
            text = (await hc.text_content() or "").strip()
            headers.append(text)
        
        resultados = []
        for row in rows:
            cells = await row.locator("td").all()
            texts = [(await c.text_content() or "").strip() for c in cells]
            if texts:
                if headers and len(headers) == len(texts):
                    resultados.append(dict(zip(headers, texts)))
                else:
                    resultados.append({
                        "radicado": texts[0] if len(texts) > 0 else "",
                        "despacho": texts[1] if len(texts) > 1 else "",
                        "ponente": texts[2] if len(texts) > 2 else "",
                        "tipo": texts[3] if len(texts) > 3 else "",
                        "fecha": texts[4] if len(texts) > 4 else "",
                    })
        return resultados

    async def close(self):
        """Cierra el navegador y libera todos los recursos."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.warning(f"Error cerrando navegador: {e}")
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.warning(f"Error deteniendo Playwright: {e}")
            self._playwright = None
        logger.info("🎭 Motor Playwright cerrado correctamente")


# Singleton global
playwright_engine = PlaywrightEngine()
