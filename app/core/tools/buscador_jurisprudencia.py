"""
Buscador de Jurisprudencia Colombiana - Estrategia Dual.

Combina dos motores de búsqueda:
1. Playwright (primario): Accede directamente a las relatorías oficiales
   de las altas cortes para obtener datos precisos de fuente primaria.
2. Brave Search API (fallback): Búsqueda web cuando Playwright falla
   o como complemento para ampliar resultados.

Arquitectura:
- La interfaz pública (buscar_jurisprudencia, validar_normatividad_documento)
  NO cambia. El skill jurisprudencia_pro/tools.py sigue funcionando sin cambios.
- Se añade enriquecimiento automático: si Playwright encuentra resultados,
  opcionalmente se complementan con Brave Search y viceversa.
"""

import logging
import json
import os
from typing import Dict, List, Optional
from app.core.http_client import StandardHTTPClient
from app.core.tools.cache import global_cache
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Query patterns específicos ampliados para mayor precisión
FUENTES_SUPPORTED = {
    "constitucional": "site:corteconstitucional.gov.co sentencia",
    "suprema": "site:cortesuprema.gov.co sentencia",
    "consejo_estado": "site:consejodeestado.gov.co sentencia",
    "sisjur": "site:alcaldiabogota.gov.co/sisjur",
    "senado_leyes": "site:secretariasenado.gov.co/senado/basedoc"
}

# Importación lazy del buscador Playwright para evitar errores si no está instalado
_playwright_buscador = None

def _get_playwright_buscador():
    """Importación lazy del buscador Playwright. Retorna None si no está disponible."""
    global _playwright_buscador
    if _playwright_buscador is None:
        try:
            from app.core.tools.buscador_jurisprudencia_playwright import buscador_jurisprudencia_pw
            _playwright_buscador = buscador_jurisprudencia_pw
            logger.info("✅ Buscador Playwright de jurisprudencia cargado correctamente")
        except ImportError as e:
            logger.warning(f"⚠️ Playwright no disponible para jurisprudencia: {e}")
            _playwright_buscador = False  # Marcador: intentado pero no disponible
        except Exception as e:
            logger.warning(f"⚠️ Error cargando buscador Playwright: {e}")
            _playwright_buscador = False
    return _playwright_buscador if _playwright_buscador is not False else None


class BuscadorJurisprudencia:
    """
    Buscador especializado para cortes colombianas.
    Estrategia dual: Playwright (fuente primaria) + Brave Search (fallback/complemento).
    Aplica caché en memoria y filtros avanzados de jurisprudencia.
    """
    def __init__(self):
        self.http_client = StandardHTTPClient()

    def _construir_query_avanzada(self, 
                                  base_query: str, 
                                  tema: str, 
                                  tipo_proceso: Optional[str] = None, 
                                  palabras_clave: Optional[List[str]] = None, 
                                  anio_inicio: Optional[int] = None, 
                                  anio_fin: Optional[int] = None) -> str:
        """
        Construye una cadena de búsqueda optimizada usando dorks y operadores lógicos.
        """
        query_parts = [base_query]

        # 1. Tipo de proceso (ej: "Acción de Tutela", "Casación Penal")
        if tipo_proceso:
            query_parts.append(f'"{tipo_proceso}"')

        # 2. Palabras clave obligatorias (ej: ["estabilidad laboral reforzada", "fuero de maternidad"])
        if palabras_clave:
            claves_formateadas = " ".join([f'"{kw.strip()}"' for kw in palabras_clave if kw.strip()])
            if claves_formateadas:
                query_parts.append(claves_formateadas)

        # 3. Tema general
        if tema:
            query_parts.append(tema)

        # 4. Filtro por rango de años (Brave Search responde muy bien a años en el texto para jurisprudencia)
        if anio_inicio and anio_fin:
            # Asegurar orden correcto
            inicio, fin = min(anio_inicio, anio_fin), max(anio_inicio, anio_fin)
            anios = " OR ".join(str(anio) for anio in range(inicio, fin + 1))
            query_parts.append(f"({anios})")
        elif anio_inicio:
            query_parts.append(str(anio_inicio))
        elif anio_fin:
            query_parts.append(str(anio_fin))

        # Unir todo asegurando que no haya espacios extra
        return " ".join(query_parts).strip()

    async def buscar(self, 
                     query: str, 
                     fuente: str = "constitucional", 
                     tipo_proceso: Optional[str] = None,
                     palabras_clave: Optional[List[str]] = None,
                     anio_inicio: Optional[int] = None,
                     anio_fin: Optional[int] = None,
                     max_results: int = 10) -> Dict:
        """
        Busca jurisprudencia con estrategia dual: Playwright → Brave Search.
        
        Flujo:
        1. Intenta Playwright (datos precisos de relatoría oficial)
        2. Si Playwright falla o no hay resultados → Brave Search API
        3. Si ambos tienen resultados → combina y deduplica
        """
        if fuente not in FUENTES_SUPPORTED:
            raise ValueError(f"Fuente no soportada. Use una de {list(FUENTES_SUPPORTED.keys())}")

        # ── FASE 1: Intentar Playwright (fuente primaria) ──
        pw_resultado = None
        pw_buscador = _get_playwright_buscador()
        
        if pw_buscador:
            try:
                logger.info(f"🎭 Intentando búsqueda Playwright en '{fuente}' para: {query}")
                pw_resultado = await pw_buscador.buscar(
                    query=query,
                    fuente=fuente,
                    tipo_proceso=tipo_proceso,
                    anio_inicio=anio_inicio,
                    anio_fin=anio_fin,
                    max_results=max_results,
                )
                
                # Verificar si Playwright tuvo éxito real (resultados no vacíos)
                if pw_resultado and "error" not in pw_resultado:
                    sentencias_pw = pw_resultado.get("sentencias", [])
                    if sentencias_pw:
                        logger.info(f"✅ Playwright encontró {len(sentencias_pw)} resultados en {fuente}")
                        # Marcar origen de cada resultado
                        for s in sentencias_pw:
                            s["origen"] = "relatoria_oficial"
                        
                        # Si Playwright encontró suficientes, retornar directamente
                        if len(sentencias_pw) >= 3:
                            return pw_resultado
                    else:
                        logger.info(f"⚠️ Playwright no encontró resultados en {fuente}, usando Brave como fallback")
                        pw_resultado = None
                else:
                    logger.info(f"⚠️ Playwright reportó error en {fuente}, usando Brave como fallback")
                    pw_resultado = None
                    
            except Exception as e:
                logger.warning(f"⚠️ Playwright falló para {fuente}: {e}. Usando Brave como fallback.")
                pw_resultado = None

        # ── FASE 2: Brave Search API (fallback o complemento) ──
        try:
            brave_resultado = await self._buscar_brave(
                query=query,
                fuente=fuente,
                tipo_proceso=tipo_proceso,
                palabras_clave=palabras_clave,
                anio_inicio=anio_inicio,
                anio_fin=anio_fin,
                max_results=max_results,
            )
        except Exception as e:
            logger.warning(f"⚠️ Falló la búsqueda en Brave Search API: {e}")
            brave_resultado = {
                "sentencias": [],
                "total_encontrado": 0,
                "fuentes_consultadas": [FUENTES_SUPPORTED[fuente]],
                "query_usada": query,
                "metodo": "brave_search",
                "error": str(e)
            }

        # ── FASE 3: Combinar resultados ──
        if pw_resultado and "error" not in pw_resultado:
            sentencias_pw = pw_resultado.get("sentencias", [])
            sentencias_brave = brave_resultado.get("sentencias", [])
            
            # Marcar origen de resultados Brave
            for s in sentencias_brave:
                s["origen"] = "brave_search"
            
            # Combinar: Playwright primero (fuente directa), luego Brave
            combinadas = sentencias_pw + sentencias_brave
            
            # Deduplicar por URL
            urls_vistas = set()
            sentencias_unicas = []
            for s in combinadas:
                url = s.get("url", "")
                if url and url in urls_vistas:
                    continue
                if url:
                    urls_vistas.add(url)
                sentencias_unicas.append(s)
            
            return {
                "sentencias": sentencias_unicas[:max_results],
                "total_encontrado": len(sentencias_unicas),
                "fuentes_consultadas": [
                    pw_resultado.get("fuente", "Relatoría Oficial"),
                    FUENTES_SUPPORTED[fuente],
                ],
                "metodo": "dual (playwright + brave)",
                "query_usada": brave_resultado.get("query_usada", query),
                "url_portal": pw_resultado.get("url_portal", ""),
            }
        
        # Solo Brave disponible
        return brave_resultado

    async def _buscar_brave(
        self,
        query: str,
        fuente: str,
        tipo_proceso: Optional[str] = None,
        palabras_clave: Optional[List[str]] = None,
        anio_inicio: Optional[int] = None,
        anio_fin: Optional[int] = None,
        max_results: int = 10,
    ) -> Dict:
        """Búsqueda en Brave Search API (motor original, ahora como método interno)."""
        # Construcción de la query optimizada
        full_query = self._construir_query_avanzada(
            base_query=FUENTES_SUPPORTED[fuente],
            tema=query,
            tipo_proceso=tipo_proceso,
            palabras_clave=palabras_clave,
            anio_inicio=anio_inicio,
            anio_fin=anio_fin
        )

        # Revisar Caché (La query completa actúa como llave única perfecta)
        cached_res = global_cache.get("brave_juris", full_query)
        if cached_res:
            logger.info(f"Búsqueda devuelta desde caché para: {full_query}")
            return cached_res
        
        api_key = os.getenv("BRAVE_API_KEY")
        
        try:
            if not api_key:
                logger.warning("BRAVE_API_KEY no encontrada. Retornando mock.")
                return {
                    "sentencias": [],
                    "total_encontrado": 0,
                    "fuentes_consultadas": [FUENTES_SUPPORTED[fuente]],
                    "query_usada": full_query,
                    "metodo": "brave_search",
                    "error": "No API Key"
                }

            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key
            }
            params = {
                "q": full_query,
                "count": max_results,
                "search_lang": "es", # Forzar resultados en español
                # Se omite 'country' porque la API de Brave Search no soporta el código 'co' o 'CO' (Colombia),
                # lo cual genera un error HTTP 422. La restricción de dominio (site:...) en la consulta
                # es más que suficiente para garantizar resultados locales.
            }

            response = await self.http_client.get(url, params=params, headers=headers)
            data = response.json()
            
            web_results = data.get("web", {}).get("results", [])
            sentencias = []
            
            for item in web_results:
                sentencias.append({
                    "titulo": item.get("title", ""),
                    "url": item.get("url", ""),
                    "resumen": item.get("description", ""),
                    "fecha_publicacion": item.get("page_age", "Fecha no especificada"),
                    "origen": "brave_search",
                })

            resultados_estructurados = {
                "sentencias": sentencias,
                "total_encontrado": len(sentencias),
                "fuentes_consultadas": [FUENTES_SUPPORTED[fuente]],
                "query_usada": full_query,
                "metodo": "brave_search",
            }
            
            global_cache.set("brave_juris", full_query, resultados_estructurados)
            
            logger.info(f"Búsqueda ejecutada en Brave. Resultados: {len(sentencias)}")
            return resultados_estructurados

        except Exception as e:
            logger.error(f"Error buscando jurisprudencia en Brave: {e}")
            raise

    async def extraer_subregla(self, url: str) -> str:
        """
        Intenta extraer de la URL de una relatoría la regla de derecho principal.
        Usa Playwright si está disponible para renderizar JavaScript, 
        con fallback a httpx para páginas estáticas.
        """
        pw_buscador = _get_playwright_buscador()
        
        if pw_buscador:
            try:
                resultado = await pw_buscador.extraer_contenido_sentencia(url)
                if resultado and "error" not in resultado:
                    contenido = resultado.get("contenido", "")
                    if contenido and len(contenido) > 100:
                        # Retornar resumen del contenido extraído
                        return f"Contenido extraído exitosamente ({resultado.get('longitud_chars', 0)} chars) de {resultado.get('titulo', url)}: {contenido[:3000]}"
            except Exception as e:
                logger.warning(f"Playwright no pudo extraer {url}: {e}, intentando httpx")
        
        # Fallback a httpx (original)
        try:
            response = await self.http_client.get(url)
            return "Contenido extraido exitosamente de " + url[:30] + "..."
        except Exception as e:
            logger.warning(f"No se pudo extraer el contenido de {url}: {e}")
            return "Contenido no disponible (Time-out o Protegido)"

    async def validar_vigencia_norma(self, norma: str) -> Dict[str, str]:
        """
        Consulta rápida para detectar si una norma (Ley, Decreto) tiene señales
        de haber sido derogada, inexequible o modificada. (Mapa de Normatividad)
        """
        query_vigencia = f'"{norma}" (derogada OR inexequible OR modificada) site:suin-juriscol.gov.co OR site:secretariasenado.gov.co'
        
        api_key = os.getenv("BRAVE_API_KEY")
        if not api_key:
            return {"norma": norma, "estado_probable": "Desconocido (No API Key)", "alerta": False}
            
        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
            params = {
                "q": query_vigencia,
                "count": 3,
                # Se omite 'country' porque la API de Brave Search no soporta 'co' o 'CO' (Colombia),
                # evitando así un error HTTP 422. Los dominios suin-juriscol.gov.co y secretariasenado.gov.co
                # limitan de forma natural los resultados a Colombia.
            }
            
            response = await self.http_client.get(url, params=params, headers=headers)
            data = response.json()
            
            web_results = data.get("web", {}).get("results", [])
            
            # Análisis heurístico simple
            alertas = 0
            resumen_hallazgos = []
            for item in web_results:
                snippet = item.get("description", "").lower()
                title = item.get("title", "").lower()
                texto_analisis = snippet + " " + title
                
                if "derogad" in texto_analisis or "inexequible" in texto_analisis or "modificad" in texto_analisis:
                    alertas += 1
                    resumen_hallazgos.append(item.get("title", ""))
                    
            if alertas >= 1:
                return {
                    "norma": norma,
                    "estado_probable": "Posiblemente Derogada/Modificada",
                    "alerta": True,
                    "hallazgos": resumen_hallazgos[:2]
                }
            else:
                return {
                    "norma": norma,
                    "estado_probable": "Vigente (sin alertas graves recientes)",
                    "alerta": False,
                    "hallazgos": []
                }
                
        except Exception as e:
            logger.error(f"Error validando vigencia de {norma}: {e}")
            return {"norma": norma, "estado_probable": "Error en consulta", "alerta": False}

# Singleton
buscador_legis = BuscadorJurisprudencia()

async def buscar_jurisprudencia(
    tema: str, 
    fuente: str = "constitucional", 
    tipo_proceso: Optional[str] = None,
    palabras_clave: Optional[List[str]] = None,
    anio_inicio: Optional[int] = None, 
    anio_fin: Optional[int] = None, 
    max_resultados: int = 5
) -> Dict:
    """
    Función de utilidad para ser llamada desde los Skills.
    Encapsula la lógica del buscador de jurisprudencia y normativa con filtros avanzados.
    Ahora usa estrategia dual: Playwright (relatoría oficial) + Brave Search (fallback).
    
    Ejemplo de uso:
    await buscar_jurisprudencia(
        tema="despido sin justa causa",
        fuente="sisjur",
        tipo_proceso="sentencia",
        palabras_clave=["estabilidad"],
        anio_inicio=2024
    )
    """
    return await buscador_legis.buscar(
        query=tema, 
        fuente=fuente, 
        tipo_proceso=tipo_proceso,
        palabras_clave=palabras_clave,
        anio_inicio=anio_inicio,
        anio_fin=anio_fin,
        max_results=max_resultados
    )

async def validar_normatividad_documento(normas: List[str]) -> List[Dict[str, str]]:
    """
    Toma una lista de normas (extraídas vía NER) y valida su vigencia.
    """
    import asyncio
    tareas = [buscador_legis.validar_vigencia_norma(norma) for norma in normas]
    resultados = await asyncio.gather(*tareas)
    return list(resultados)