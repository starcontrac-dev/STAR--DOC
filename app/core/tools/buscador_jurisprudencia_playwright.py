"""
Buscador de Jurisprudencia con Playwright.

Consulta directamente las relatorías oficiales de las altas cortes colombianas
usando un navegador headless (Playwright) para renderizar SPAs y portales JSF.

Portales soportados:
- Corte Constitucional (Angular SPA)
- Corte Suprema de Justicia (JSF/PrimeFaces)
- Consejo de Estado (JSF/PrimeFaces)
- SISJUR - Alcaldía de Bogotá
- Secretaría del Senado

Patrón: Mismo que buscador_expedientes.py (playwright_engine singleton).
Uso: Se invoca como estrategia primaria desde buscador_jurisprudencia.py,
     con fallback a Brave Search API si Playwright falla.
"""

import logging
import asyncio
from typing import Dict, Optional, List

from app.core.browser_engine import playwright_engine, run_in_playwright_thread
from app.core.tools.cargador_selectores import obtener_selectores_actualizados
from app.core.tools.cache import global_cache
from tenacity import retry, wait_exponential, stop_after_attempt

logger = logging.getLogger(__name__)

# Mapeo de fuentes a claves de selectores
FUENTES_PLAYWRIGHT = {
    "constitucional": "constitucional",
    "suprema": "suprema",
    "consejo_estado": "consejo_estado",
    "sisjur": "sisjur",
    "senado_leyes": "senado_leyes",
}


class BuscadorJurisprudenciaPlaywright:
    """
    Buscador de jurisprudencia usando Playwright para acceder
    directamente a las relatorías oficiales de las cortes colombianas.
    
    Características:
    - Renderiza SPAs (Angular, JSF/PrimeFaces) con JavaScript
    - Anti-detección con playwright-stealth
    - Cache integrado (24h via global_cache)
    - Rate limiting (vía playwright_engine)
    - Extracción estructurada de resultados
    """

    @run_in_playwright_thread
    async def buscar(
        self,
        query: str,
        fuente: str = "constitucional",
        tipo_proceso: Optional[str] = None,
        anio_inicio: Optional[int] = None,
        anio_fin: Optional[int] = None,
        max_results: int = 10,
    ) -> Dict:
        """
        Busca jurisprudencia en la relatoría oficial de la fuente indicada.

        Args:
            query: Término de búsqueda (tema, sentencia, norma)
            fuente: Clave de la fuente (constitucional, suprema, consejo_estado, sisjur, senado_leyes)
            tipo_proceso: Tipo de proceso para filtrar (ej: Tutela, Casación)
            anio_inicio: Año inicial del rango de búsqueda
            anio_fin: Año final del rango de búsqueda
            max_results: Número máximo de resultados a extraer

        Returns:
            Dict con sentencias encontradas o error descriptivo
        """
        if fuente not in FUENTES_PLAYWRIGHT:
            return {
                "error": f"Fuente '{fuente}' no soportada para Playwright.",
                "fuentes_disponibles": list(FUENTES_PLAYWRIGHT.keys()),
            }

        # Construir texto de búsqueda enriquecido
        search_text = self._construir_texto_busqueda(query, tipo_proceso)

        # Verificar cache
        cache_key = f"pw_{fuente}_{search_text}_{anio_inicio}_{anio_fin}"
        cached = global_cache.get("playwright_juris", cache_key)
        if cached:
            logger.info(f"📦 Cache hit Playwright: {fuente} -> {query}")
            return cached

        # Despachar al método específico según la fuente
        try:
            if fuente == "constitucional":
                resultado = await self._buscar_corte_constitucional(
                    search_text, anio_inicio, anio_fin, max_results
                )
            elif fuente in ("suprema", "consejo_estado"):
                resultado = await self._buscar_relatoria_jsf(
                    fuente, search_text, anio_inicio, anio_fin, max_results
                )
            elif fuente in ("sisjur", "senado_leyes"):
                resultado = await self._buscar_portal_simple(
                    fuente, search_text, max_results
                )
            else:
                return {"error": f"Fuente '{fuente}' sin implementación Playwright."}

            # Cachear resultado exitoso
            if resultado and "error" not in resultado:
                global_cache.set("playwright_juris", cache_key, resultado)

            return resultado

        except Exception as e:
            logger.error(f"❌ Error Playwright buscando en {fuente}: {e}")
            return {
                "error": f"Error Playwright en {fuente}: {str(e)}",
                "fuente": fuente,
                "query": query,
                "sugerencia": "Se usará Brave Search como fallback.",
            }

    def _construir_texto_busqueda(
        self, query: str, tipo_proceso: Optional[str] = None
    ) -> str:
        """Construye el texto de búsqueda combinando query y tipo de proceso."""
        parts = []
        if tipo_proceso:
            parts.append(tipo_proceso)
        parts.append(query)
        return " ".join(parts).strip()

    # ── Corte Constitucional (Angular SPA) ──────────────────────────────

    async def _buscar_corte_constitucional(
        self,
        search_text: str,
        anio_inicio: Optional[int],
        anio_fin: Optional[int],
        max_results: int,
    ) -> Dict:
        """Busca sentencias en la relatoría de la Corte Constitucional."""
        sel = await obtener_selectores_actualizados("constitucional", tipo="selectores_jurisprudencia")
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)

        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_cc():
            logger.info(f"🔍 Playwright CC (intento): buscando '{search_text}'")
            await page.goto(sel["url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["wait_for"], state="visible", timeout=15000)

            # Seleccionar categoría "Texto completo" por defecto
            try:
                select_el = page.locator(sel["select_categoria"]).first
                if await select_el.count() > 0:
                    await select_el.select_option(value=sel["categorias"]["texto_completo"])
                    await asyncio.sleep(0.3)
            except Exception:
                pass  # Si no hay select, continuar con búsqueda simple

            # Llenar campo de búsqueda con tipeo humanoide
            await playwright_engine.type_like_human(page, sel["input_busqueda"], search_text)

            # Aplicar filtros de fecha si se proporcionan
            if anio_inicio:
                try:
                    fecha_desde = page.locator(sel["input_fecha_inicio"]).first
                    if await fecha_desde.count() > 0:
                        await fecha_desde.fill(f"{anio_inicio}-01-01")
                except Exception:
                    pass
            if anio_fin:
                try:
                    fecha_hasta = page.locator(sel["input_fecha_fin"]).first
                    if await fecha_hasta.count() > 0:
                        await fecha_hasta.fill(f"{anio_fin}-12-31")
                except Exception:
                    pass

            # Pausa anti-bot y click en buscar
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_cc()

            # Esperar resultados (Angular renderiza dinámicamente)
            await asyncio.sleep(3)
            try:
                await page.wait_for_selector(
                    sel["contenedor_resultados"],
                    state="visible",
                    timeout=20000,
                )
            except Exception:
                await asyncio.sleep(3)

            # Extraer resultados
            sentencias = await self._extraer_resultados_angular(page, sel, max_results)

            return {
                "sentencias": sentencias,
                "total_encontrado": len(sentencias),
                "fuente": "Corte Constitucional (Relatoría Oficial)",
                "metodo": "playwright",
                "query_usada": search_text,
                "url_portal": sel["url"],
            }

        except Exception as e:
            logger.error(f"❌ Error en CC Playwright: {e}")
            return {"error": f"Error consultando Corte Constitucional: {str(e)}"}
        finally:
            await page.close()
            await context.close()

    async def _extraer_resultados_angular(
        self, page, sel: Dict, max_results: int
    ) -> List[Dict]:
        """Extrae resultados de la SPA Angular de la Corte Constitucional."""
        sentencias = []
        try:
            # Intentar extraer items individuales de resultados
            items = await page.locator(sel["item_resultado"]).all()
            if not items:
                # Fallback: extraer todo el texto del contenedor
                contenedor = page.locator(sel["contenedor_resultados"]).first
                if await contenedor.count() > 0:
                    texto = await contenedor.inner_text()
                    if texto and texto.strip():
                        return [{"texto_completo": texto[:8000], "tipo": "texto_raw"}]
                return []

            for i, item in enumerate(items[:max_results]):
                try:
                    texto = (await item.inner_text() or "").strip()
                    # Intentar extraer enlace
                    link = ""
                    links = await item.locator("a").all()
                    if links:
                        link = await links[0].get_attribute("href") or ""
                        if link and not link.startswith("http"):
                            link = f"https://www.corteconstitucional.gov.co{link}"

                    # Parsear título y resumen del texto
                    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
                    titulo = lineas[0] if lineas else "Sin título"
                    resumen = " ".join(lineas[1:3]) if len(lineas) > 1 else ""

                    sentencias.append({
                        "titulo": titulo[:200],
                        "url": link,
                        "resumen": resumen[:500],
                        "fuente_directa": True,
                    })
                except Exception as item_err:
                    logger.debug(f"Error extrayendo item {i}: {item_err}")
                    continue

        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo resultados Angular: {e}")

        return sentencias

    # ── Corte Suprema y Consejo de Estado (JSF/PrimeFaces) ──────────────

    async def _buscar_relatoria_jsf(
        self,
        fuente: str,
        search_text: str,
        anio_inicio: Optional[int],
        anio_fin: Optional[int],
        max_results: int,
    ) -> Dict:
        """Busca sentencias en relatorías JSF/PrimeFaces (CSJ o CE)."""
        sel = await obtener_selectores_actualizados(fuente, tipo="selectores_jurisprudencia")
        nombre_fuente = "Corte Suprema de Justicia" if fuente == "suprema" else "Consejo de Estado"
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)

        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_jsf():
            logger.info(f"🔍 Playwright {fuente} (intento): buscando '{search_text}'")
            await page.goto(sel["url"], wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["wait_for"], state="visible", timeout=15000)

            # Llenar campo de búsqueda con tipeo humanoide
            await playwright_engine.type_like_human(page, sel["input_busqueda"], search_text)

            # Aplicar filtros de fecha si disponibles
            if anio_inicio:
                try:
                    f_desde = page.locator(sel["input_fecha_desde"]).first
                    if await f_desde.count() > 0:
                        await f_desde.fill(f"01/01/{anio_inicio}")
                except Exception:
                    pass
            if anio_fin:
                try:
                    f_hasta = page.locator(sel["input_fecha_hasta"]).first
                    if await f_hasta.count() > 0:
                        await f_hasta.fill(f"31/12/{anio_fin}")
                except Exception:
                    pass

            # Click en buscar
            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_jsf()

            # Esperar resultados (PrimeFaces usa AJAX parcial)
            await asyncio.sleep(3)
            try:
                await page.wait_for_selector(
                    sel["contenedor_resultados"],
                    state="visible",
                    timeout=25000,
                )
            except Exception:
                await asyncio.sleep(3)

            # Extraer resultados de la datatable PrimeFaces
            sentencias = await self._extraer_resultados_jsf(page, sel, max_results)

            return {
                "sentencias": sentencias,
                "total_encontrado": len(sentencias),
                "fuente": f"{nombre_fuente} (Relatoría Oficial)",
                "metodo": "playwright",
                "query_usada": search_text,
                "url_portal": sel["url"],
            }

        except Exception as e:
            logger.error(f"❌ Error en {fuente} Playwright: {e}")
            return {"error": f"Error consultando {nombre_fuente}: {str(e)}"}
        finally:
            await page.close()
            await context.close()

    async def _extraer_resultados_jsf(
        self, page, sel: Dict, max_results: int
    ) -> List[Dict]:
        """Extrae resultados de datatables PrimeFaces (CSJ/CE)."""
        sentencias = []
        try:
            filas = await page.locator(sel["fila_resultado"]).all()
            if not filas:
                # Fallback: texto completo del contenedor
                cont = page.locator(sel["contenedor_resultados"]).first
                if await cont.count() > 0:
                    texto = await cont.inner_text()
                    if texto and texto.strip():
                        return [{"texto_completo": texto[:8000], "tipo": "texto_raw"}]
                return []

            for i, fila in enumerate(filas[:max_results]):
                try:
                    celdas = await fila.locator("td").all()
                    textos = [(await c.text_content() or "").strip() for c in celdas]
                    if not textos or not any(textos):
                        continue

                    # Intentar extraer enlace de la fila
                    link = ""
                    links = await fila.locator("a").all()
                    if links:
                        link = await links[0].get_attribute("href") or ""

                    sentencias.append({
                        "titulo": textos[0] if textos else "Sin título",
                        "radicado": textos[1] if len(textos) > 1 else "",
                        "fecha": textos[2] if len(textos) > 2 else "",
                        "ponente": textos[3] if len(textos) > 3 else "",
                        "resumen": textos[4] if len(textos) > 4 else "",
                        "url": link,
                        "fuente_directa": True,
                    })
                except Exception as row_err:
                    logger.debug(f"Error extrayendo fila {i}: {row_err}")
                    continue

        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo resultados JSF: {e}")

        return sentencias

    # ── SISJUR y Senado (portales HTML simples) ─────────────────────────

    async def _buscar_portal_simple(
        self, fuente: str, search_text: str, max_results: int
    ) -> Dict:
        """Busca normativa en portales HTML tradicionales (SISJUR, Senado)."""
        sel = await obtener_selectores_actualizados(fuente, tipo="selectores_jurisprudencia")
        nombre = "SISJUR (Alcaldía de Bogotá)" if fuente == "sisjur" else "Secretaría del Senado"
        url = sel.get("url_busqueda", sel["url"])
        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)

        @retry(
            wait=wait_exponential(multiplier=1, min=2, max=6),
            stop=stop_after_attempt(2),
            reraise=True
        )
        async def navegar_y_llenar_simple():
            logger.info(f"🔍 Playwright {fuente} (intento): buscando '{search_text}'")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector(sel["wait_for"], state="visible", timeout=15000)

            # Llenar campo de búsqueda con tipeo humanoide
            await playwright_engine.type_like_human(page, sel["input_busqueda"], search_text)

            await asyncio.sleep(0.5)
            await page.locator(sel["btn_buscar"]).first.click()

        try:
            await navegar_y_llenar_simple()

            # Esperar carga de resultados
            await asyncio.sleep(3)
            try:
                await page.wait_for_selector(
                    sel["contenedor_resultados"],
                    state="visible",
                    timeout=20000,
                )
            except Exception:
                await asyncio.sleep(2)

            # Extraer enlaces y texto de resultados
            sentencias = await self._extraer_resultados_simple(page, sel, max_results)

            return {
                "sentencias": sentencias,
                "total_encontrado": len(sentencias),
                "fuente": f"{nombre} (Portal Oficial)",
                "metodo": "playwright",
                "query_usada": search_text,
                "url_portal": url,
            }

        except Exception as e:
            logger.error(f"❌ Error en {fuente} Playwright: {e}")
            return {"error": f"Error consultando {nombre}: {str(e)}"}
        finally:
            await page.close()
            await context.close()

    async def _extraer_resultados_simple(
        self, page, sel: Dict, max_results: int
    ) -> List[Dict]:
        """Extrae resultados de portales HTML simples."""
        sentencias = []
        try:
            # Buscar enlaces relevantes dentro del contenedor
            link_sel = sel.get("link_norma", sel.get("link_ley", "a"))
            links = await page.locator(
                f"{sel['contenedor_resultados']} {link_sel}"
            ).all()

            if not links:
                # Fallback: todos los links del contenedor
                links = await page.locator(
                    f"{sel['contenedor_resultados']} a"
                ).all()

            if not links:
                # Último fallback: texto completo
                cont = page.locator(sel["contenedor_resultados"]).first
                if await cont.count() > 0:
                    texto = await cont.inner_text()
                    if texto and texto.strip():
                        return [{"texto_completo": texto[:8000], "tipo": "texto_raw"}]
                return []

            for i, link in enumerate(links[:max_results]):
                try:
                    titulo = (await link.text_content() or "").strip()
                    href = await link.get_attribute("href") or ""
                    if titulo and len(titulo) > 3:
                        sentencias.append({
                            "titulo": titulo[:200],
                            "url": href,
                            "fuente_directa": True,
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"⚠️ Error extrayendo resultados simples: {e}")

        return sentencias

    @run_in_playwright_thread
    async def extraer_contenido_sentencia(self, url: str) -> Dict:
        """
        Navega a la URL de una sentencia y extrae su contenido textual.
        Útil para obtener el texto completo de sentencias encontradas.

        Args:
            url: URL directa de la sentencia

        Returns:
            Dict con el contenido extraído
        """
        if not url or not url.startswith("http"):
            return {"error": "URL inválida", "url": url}

        cache_key = f"sentencia_{url}"
        cached = global_cache.get("playwright_sentencia", cache_key)
        if cached:
            return cached

        context = await playwright_engine.create_context()
        page = await playwright_engine.create_stealth_page(context)

        try:
            logger.info(f"📄 Extrayendo contenido de: {url}")
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await asyncio.sleep(2)

            # Extraer título de la página
            titulo = await page.title() or "Sin título"

            # Extraer contenido principal (buscar en orden de prioridad)
            contenido = ""
            selectores_contenido = [
                "article", ".contenido", "#contenido", ".texto-sentencia",
                ".body-content", "main", ".content", "#content",
                ".sentencia-texto", ".documento",
            ]
            for sel_cont in selectores_contenido:
                try:
                    el = page.locator(sel_cont).first
                    if await el.count() > 0:
                        contenido = await el.inner_text()
                        if contenido and len(contenido) > 100:
                            break
                except Exception:
                    continue

            # Fallback: todo el body
            if not contenido or len(contenido) < 100:
                contenido = await page.locator("body").inner_text()

            resultado = {
                "titulo": titulo,
                "url": url,
                "contenido": contenido[:15000],  # Limitar a 15K caracteres
                "longitud_chars": len(contenido),
            }

            global_cache.set("playwright_sentencia", cache_key, resultado)
            return resultado

        except Exception as e:
            logger.error(f"❌ Error extrayendo sentencia de {url}: {e}")
            return {"error": f"Error extrayendo contenido: {str(e)}", "url": url}
        finally:
            await page.close()
            await context.close()


# Singleton global
buscador_jurisprudencia_pw = BuscadorJurisprudenciaPlaywright()
