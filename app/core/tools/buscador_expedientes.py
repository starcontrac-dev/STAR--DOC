"""
Buscador de Expedientes Judiciales usando Playwright.

Implementa consultas a los portales judiciales colombianos:
- Rama Judicial (consultaprocesos.ramajudicial.gov.co) - Vue.js SPA
- SAMAI (samai.consejodeestado.gov.co) - ASP.NET
- Corte Constitucional (corteconstitucional.gov.co/relatoria/)

Usa Playwright para renderizar JavaScript y extraer datos
de SPAs que no funcionan con httpx/requests.
"""

import logging
import asyncio
from typing import Dict, Optional, List

from app.core.browser_engine import playwright_engine, run_in_playwright_thread
from app.core.tools.cargador_selectores import obtener_selectores_actualizados
from tenacity import retry, wait_exponential, stop_after_attempt

logger = logging.getLogger(__name__)

# Cache local simple (TTL 1 hora) para evitar peticiones repetidas
_cache: Dict[str, Dict] = {}
_cache_ttl: Dict[str, float] = {}

def _get_cached(key: str) -> Optional[Dict]:
    """Obtiene un resultado del cache si no ha expirado (TTL 1 hora)."""
    import time
    if key in _cache and key in _cache_ttl:
        if time.time() - _cache_ttl[key] < 3600:  # 1 hora
            logger.info(f"📦 Cache hit: {key}")
            return _cache[key]
        else:
            del _cache[key]
            del _cache_ttl[key]
    return None

def _set_cached(key: str, value: Dict):
    """Almacena un resultado en cache con timestamp."""
    import time
    _cache[key] = value
    _cache_ttl[key] = time.time()


class BuscadorExpedientes:
    """Buscador de expedientes judiciales usando Playwright."""

    @run_in_playwright_thread
    async def consultar_por_radicacion(self, numero_radicacion: str) -> Dict:
        """
        Consulta proceso por número de radicación en consultaprocesos.ramajudicial.gov.co
        
        Args:
            numero_radicacion: Número de radicación del proceso (ej: 11001-31-03-027-2024-00123-00)
            
        Returns:
            Dict con resultados del proceso o error
        """
        cache_key = f"rad_{numero_radicacion}"
        cached = _get_cached(cache_key)
        if cached:
            return cached

        sel = await obtener_selectores_actualizados("rama_judicial")
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)
        
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar():
            logger.info(f"🔍 Consultando radicación (intento): {numero_radicacion}")
            await page.goto(sel["url_radicacion"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["input_radicacion"], state="visible", timeout=15000)
            await playwright_engine.type_like_human(page, sel["input_radicacion"], numero_radicacion)
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar()
            
            # Verificar si apareció un CAPTCHA inmediatamente después
            await asyncio.sleep(1)
            captcha_count = await page.locator(".slider-captcha, #g-recaptcha, iframe[title*='recaptcha'], iframe[src*='recaptcha'], .captcha").count()
            if captcha_count > 0:
                logger.warning(f"CAPTCHA detectado al consultar radicación {numero_radicacion}")
                return {
                    "error": "El portal judicial requiere validación humana (CAPTCHA).",
                    "numero_radicacion": numero_radicacion,
                    "portal": "consultaprocesos.ramajudicial.gov.co",
                    "sugerencia": "Por favor, inténtalo más tarde o consulta directamente en la página web oficial."
                }

            # Esperar resultados (tabla) o indicador de no resultados
            try:
                await page.wait_for_selector(
                    f"{sel['tabla_resultados']}, {sel['no_results']}", 
                    state="visible", 
                    timeout=30000
                )
            except Exception as wait_err:
                # Si no aparece tabla ni "no results", verificar de nuevo si hay captcha
                captcha_count2 = await page.locator("iframe[title*='recaptcha'], iframe[src*='recaptcha']").count()
                if captcha_count2 > 0:
                    return {
                        "error": "El portal judicial bloqueó la solicitud (CAPTCHA invisible detectado).",
                        "numero_radicacion": numero_radicacion,
                        "portal": "consultaprocesos.ramajudicial.gov.co"
                    }
                logger.warning(f"Timeout esperando resultados para {numero_radicacion}: {wait_err}")
                await asyncio.sleep(1)
            
            # Verificar si hay resultados
            no_results = await page.locator(sel["no_results"]).count()
            if no_results > 0:
                return {
                    "numero_radicacion": numero_radicacion,
                    "resultados": [],
                    "portal": "consultaprocesos.ramajudicial.gov.co",
                    "total": 0,
                    "mensaje": "No se encontraron procesos con esa radicación."
                }
            
            # Extraer datos de la tabla
            resultados = await self._extraer_tabla(page, sel["tabla_resultados"])
            
            resultado = {
                "numero_radicacion": numero_radicacion,
                "resultados": resultados,
                "portal": "consultaprocesos.ramajudicial.gov.co",
                "total": len(resultados)
            }
            
            _set_cached(cache_key, resultado)
            logger.info(f"✅ Encontrados {len(resultados)} resultados para radicación {numero_radicacion}")
            return resultado
            
        except Exception as e:
            error_msg = str(e) or repr(e)
            logger.error(f"❌ Error consultando radicación {numero_radicacion}: {error_msg}")
            return {
                "error": f"Error consultando el portal judicial: {error_msg}",
                "numero_radicacion": numero_radicacion,
                "portal": "consultaprocesos.ramajudicial.gov.co",
                "sugerencia": "El portal puede estar temporalmente fuera de servicio o cambió su estructura."
            }
        finally:
            await page.close()
            await context.close()

    @run_in_playwright_thread
    async def consultar_por_nombre(self, nombre: str) -> Dict:
        """
        Busca procesos por nombre o razón social en consultaprocesos.ramajudicial.gov.co
        
        Args:
            nombre: Nombre completo o razón social a buscar
            
        Returns:
            Dict con resultados encontrados
        """
        cache_key = f"nombre_{nombre.lower().strip()}"
        cached = _get_cached(cache_key)
        if cached:
            return cached

        sel = await obtener_selectores_actualizados("rama_judicial")
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)
        
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_nombre():
            logger.info(f"🔍 Consultando por nombre (intento): {nombre}")
            await page.goto(sel["url_nombre"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["input_nombre"], state="visible", timeout=15000)
            await playwright_engine.type_like_human(page, sel["input_nombre"], nombre)
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_nombre()
            
            try:
                await page.wait_for_selector(
                    f"{sel['tabla_resultados']}, {sel['no_results']}",
                    state="visible", timeout=30000
                )
            except Exception:
                await asyncio.sleep(3)
            
            resultados = await self._extraer_tabla(page, sel["tabla_resultados"])
            
            resultado = {
                "nombre_buscado": nombre,
                "resultados": resultados,
                "portal": "consultaprocesos.ramajudicial.gov.co",
                "total": len(resultados)
            }
            
            _set_cached(cache_key, resultado)
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error consultando nombre {nombre}: {e}")
            return {
                "error": f"Error consultando por nombre: {str(e)}",
                "nombre_buscado": nombre,
                "sugerencia": "Verifica que el nombre esté correctamente escrito."
            }
        finally:
            await page.close()
            await context.close()

    @run_in_playwright_thread
    async def consultar_samai(self, radicado: str) -> Dict:
        """
        Consulta procesos contencioso-administrativos en SAMAI (Consejo de Estado).
        
        Args:
            radicado: Número de radicado del proceso
        """
        cache_key = f"samai_{radicado}"
        cached = _get_cached(cache_key)
        if cached:
            return cached

        sel = await obtener_selectores_actualizados("samai")
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)
        
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_samai():
            logger.info(f"🔍 Consultando SAMAI (intento): {radicado}")
            await page.goto(sel["url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["input_radicado"], state="visible", timeout=15000)
            await playwright_engine.type_like_human(page, sel["input_radicado"], radicado)
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_samai()
            
            try:
                await page.wait_for_selector(sel["tabla_resultados"], state="visible", timeout=30000)
            except Exception:
                await asyncio.sleep(3)
            
            resultados = await self._extraer_tabla(page, sel["tabla_resultados"])
            
            resultado = {
                "radicado": radicado,
                "resultados": resultados,
                "portal": "samai.consejodeestado.gov.co",
                "total": len(resultados)
            }
            
            _set_cached(cache_key, resultado)
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error consultando SAMAI {radicado}: {e}")
            return {
                "error": f"Error consultando SAMAI: {str(e)}",
                "radicado": radicado,
                "sugerencia": "El portal SAMAI puede tener restricciones de acceso. Intenta de nuevo."
            }
        finally:
            await page.close()
            await context.close()

    @run_in_playwright_thread
    async def consultar_sentencia_cc(self, sentencia: str) -> Dict:
        """
        Busca sentencias en la Relatoría de la Corte Constitucional.
        
        Args:
            sentencia: Número de sentencia (ej: T-123/2025, C-456/2024, SU-789/2023)
        """
        cache_key = f"cc_{sentencia}"
        cached = _get_cached(cache_key)
        if cached:
            return cached

        sel = await obtener_selectores_actualizados("corte_constitucional")
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)
        
        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_cc():
            logger.info(f"🔍 Consultando Corte Constitucional (intento): {sentencia}")
            await page.goto(sel["url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["input_busqueda"], state="visible", timeout=15000)
            await playwright_engine.type_like_human(page, sel["input_busqueda"], sentencia)
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_cc()
            
            try:
                await page.wait_for_selector(sel["resultados"], state="visible", timeout=30000)
            except Exception:
                await asyncio.sleep(3)
            
            # Extraer texto de resultados
            results_html = await page.locator(sel["resultados"]).first.inner_text()
            
            resultado = {
                "sentencia": sentencia,
                "contenido": results_html[:10000] if results_html else "Sin resultados",
                "portal": "corteconstitucional.gov.co/relatoria",
                "url_consulta": f"{sel['url']}?buscar={sentencia}"
            }
            
            _set_cached(cache_key, resultado)
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error consultando CC {sentencia}: {e}")
            return {
                "error": f"Error consultando Corte Constitucional: {str(e)}",
                "sentencia": sentencia,
                "sugerencia": "Verifica el formato de la sentencia (ej: T-123/2025)."
            }
        finally:
            await page.close()
            await context.close()

    async def _extraer_tabla(self, page, table_selector: str) -> List[Dict]:
        """Extrae filas de una tabla HTML de resultados."""
        try:
            # Verificar que la tabla existe
            table_count = await page.locator(table_selector).count()
            if table_count == 0:
                return []
            
            return await playwright_engine.extract_table_data(page, table_selector)
        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo tabla: {e}")
            # Fallback: extraer todo el texto visible
            try:
                text = await page.locator(table_selector).first.inner_text()
                return [{"texto_completo": text[:5000]}] if text else []
            except Exception:
                return []


# Singleton global
buscador_expedientes = BuscadorExpedientes()
