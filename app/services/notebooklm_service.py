"""
Servicio NotebookLM v2.0 para STAR-DOC.

Interfaz Python hacia el MCP de NotebookLM con:
- Retry con backoff exponencial y circuit breaker
- Gestión de sesiones multi-turno (session_id)
- Sistema de citaciones jurídicas (source_format)
- Caché inteligente con invalidación por mutación
- Batch query concurrente real con semáforo
- Health check proactivo

Patrón: Singleton Thread-Safe
Comunicación: MCP Python SDK (ClientSession + stdio_client)
"""

import json
import asyncio
import logging
import os
import re
import time
import shutil
import platform
import threading
import random
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from functools import wraps

logger = logging.getLogger(__name__)

# --- SDK MCP ---
try:
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    MCP_SDK_AVAILABLE = True
except ImportError:
    MCP_SDK_AVAILABLE = False
    logger.warning("SDK MCP no disponible. Instala con: pip install mcp")


# ══════════════════════════════════════════════════════════
# CLASIFICACIÓN DE ERRORES MCP
# ══════════════════════════════════════════════════════════

class MCPErrorType(Enum):
    """Tipos de error del servidor MCP para manejo diferenciado."""
    AUTH = "auth_error"           # Autenticación expirada o inválida
    TIMEOUT = "timeout_error"     # Operación excedió el tiempo límite
    RATE_LIMIT = "rate_limit"     # Límite de consultas diarias alcanzado
    NOT_FOUND = "not_found"       # Recurso no encontrado
    CONNECTION = "connection"     # Error de conexión al proceso MCP
    INTERNAL = "internal_error"   # Error interno del servidor MCP
    UNAVAILABLE = "unavailable"   # Servicio no disponible


@dataclass
class MCPError:
    """Error estructurado del MCP con contexto rico para diagnóstico."""
    error_type: MCPErrorType
    message: str
    tool_name: str = ""
    retryable: bool = False
    details: Optional[str] = None

    def to_dict(self) -> dict:
        """Convierte a diccionario para respuestas API."""
        result = {
            "error": self.message,
            "error_type": self.error_type.value,
            "retryable": self.retryable
        }
        if self.details:
            result["details"] = self.details
        return result


def _classify_error(exception: Exception, tool_name: str = "") -> MCPError:
    """Clasifica una excepción en un MCPError tipado."""
    msg = str(exception).lower()

    if isinstance(exception, asyncio.TimeoutError):
        return MCPError(MCPErrorType.TIMEOUT, f"Timeout ejecutando '{tool_name}'.", tool_name, retryable=True)
    if isinstance(exception, FileNotFoundError):
        return MCPError(MCPErrorType.CONNECTION, "notebooklm-mcp no encontrado en PATH.", tool_name)
    if "rate limit" in msg or "too many" in msg or "quota" in msg:
        return MCPError(MCPErrorType.RATE_LIMIT, "Límite de consultas alcanzado.", tool_name, details="Usa re_auth para cambiar de cuenta.")
    if "auth" in msg or "login" in msg or "unauthorized" in msg:
        return MCPError(MCPErrorType.AUTH, "Autenticación expirada.", tool_name, retryable=True, details="Ejecuta setup_auth.")
    if "not found" in msg:
        return MCPError(MCPErrorType.NOT_FOUND, str(exception), tool_name)
    if isinstance(exception, (ConnectionError, OSError)):
        return MCPError(MCPErrorType.CONNECTION, str(exception), tool_name, retryable=True)

    return MCPError(MCPErrorType.INTERNAL, str(exception), tool_name, retryable=False)


# ══════════════════════════════════════════════════════════
# CIRCUIT BREAKER — Protección contra cascadas de fallos
# ══════════════════════════════════════════════════════════

class CircuitBreaker:
    """Implementación simple de circuit breaker para el MCP."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure_time: float = 0.0
        self._state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open":
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = "half-open"
            return self._state

    def record_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                logger.warning(f"🔴 Circuit Breaker ABIERTO tras {self._failure_count} fallos consecutivos.")

    def is_allowed(self) -> bool:
        return self.state != "open"

# ══════════════════════════════════════════════════════════
# TAXONOMÍA Y CONSTANTES JURÍDICAS
# ══════════════════════════════════════════════════════════

LEGAL_TAGS = {
    "constitucional": "#legal-constitucional",
    "administrativo": "#legal-administrativo",
    "comercial": "#legal-comercial",
    "civil": "#legal-civil",
    "tributario": "#legal-tributario",
    "laboral": "#legal-laboral",
    "penal": "#legal-penal",
    "crypto": "#legal-crypto",
    "inmobiliario": "#legal-inmobiliario",
}

JURIS_TAGS = {
    "corte_constitucional": "#juris-corte_constitucional",
    "corte_suprema": "#juris-corte_suprema",
    "consejo_estado": "#juris-consejo_estado",
}

TAG_LEGAL_ROOT = "#legal"
TAG_JURIS_ROOT = "#juris"

# --- Ruta al ejecutable MCP ---
NOTEBOOKLM_MCP_EXE = shutil.which("notebooklm-mcp") or shutil.which("notebooklm-mcp.exe")

# --- Detección de Rutas Multi-plataforma Segura ---
def get_mcp_library_path() -> Path:
    """
    Detecta de forma robusta la ruta de la librería indexada por el MCP según el SO.
    Retorna un objeto Path para manejo seguro.
    """
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base_dir = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
    elif system == "Darwin":
        base_dir = home / "Library" / "Application Support"
    else:
        # Linux y otros Unix adaptando el estándar XDG
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base_dir = Path(xdg_data) if xdg_data else home / ".local" / "share"
        
    return base_dir / "notebooklm-mcp" / "Data" / "library.json"

# Ruta de la librería local del MCP (índice de notebooks)
LIBRARY_PATH = get_mcp_library_path()


@dataclass
class NotebookEntry:
    """Entrada de un cuaderno indexado localmente."""
    notebook_id: str
    title: str
    tags: List[str] = field(default_factory=list)
    source_count: int = 0
    last_queried: Optional[str] = None
    summary: Optional[str] = None


class NotebookLMService:
    """
    Servicio Singleton v2.0 para interactuar con NotebookLM via MCP SDK.

    Mejoras v2.0:
    - Retry con backoff exponencial y jitter
    - Circuit breaker para protección contra cascadas
    - Sesiones multi-turno con session_id tracking
    - Sistema de citaciones (source_format)
    - Caché inteligente con invalidación por mutación
    - Batch query concurrente con semáforo
    - Health check proactivo
    """
    _instance: Optional['NotebookLMService'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'NotebookLMService':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # --- Caché de notebooks ---
        self._cache: Dict[str, NotebookEntry] = {}
        self._cache_ts: float = 0.0
        self._cache_ttl: int = 300  # 5 minutos

        # --- Configuración MCP ---
        self._mcp_exe = NOTEBOOKLM_MCP_EXE

        # --- Circuit Breaker ---
        self._circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)

        # --- Semáforo de concurrencia (máx. 3 llamadas MCP simultáneas) ---
        self._mcp_semaphore = asyncio.Semaphore(3)

        # --- Tracking de sesiones multi-turno ---
        self._sessions: Dict[str, str] = {}  # notebook_id -> session_id

        # --- Formato de citaciones por defecto (ideal para uso jurídico) ---
        self.default_source_format: str = "footnotes"

        # --- Métricas internas ---
        self._stats = {"calls": 0, "errors": 0, "retries": 0, "cache_hits": 0}

        self._initialized = True

        if not self._mcp_exe:
            logger.warning(
                "Ejecutable notebooklm-mcp no encontrado en PATH. "
                "Las herramientas de NotebookLM no funcionarán."
            )
        elif not MCP_SDK_AVAILABLE:
            logger.warning("SDK MCP no instalado. Instala con: pip install mcp")
        else:
            logger.info(f"NotebookLMService v2.0 inicializado. MCP: {self._mcp_exe}")

        self._load_local_library()

    # ──────────────────────────────────────────────────────────
    # COMUNICACIÓN CON EL MCP (SDK OFICIAL)
    # ──────────────────────────────────────────────────────────

    async def _call_mcp(
        self,
        tool_name: str,
        arguments: dict,
        timeout: float = 90.0,
        max_retries: int = 2
    ) -> dict:
        """
        Ejecuta una llamada al MCP con:
        - Semáforo de concurrencia (máx. 3 simultáneas)
        - Circuit breaker (protección contra cascadas)
        - Retry con backoff exponencial + jitter
        - Clasificación de errores tipada
        """
        if not self._mcp_exe:
            return MCPError(MCPErrorType.UNAVAILABLE, "notebooklm-mcp no instalado.", tool_name).to_dict()
        if not MCP_SDK_AVAILABLE:
            return MCPError(MCPErrorType.UNAVAILABLE, "SDK MCP no disponible.", tool_name).to_dict()

        # Verificar circuit breaker
        if not self._circuit_breaker.is_allowed():
            return MCPError(
                MCPErrorType.UNAVAILABLE,
                "Servicio temporalmente suspendido (circuit breaker abierto).",
                tool_name, retryable=True,
                details=f"Se reabrirá en {self._circuit_breaker._recovery_timeout}s."
            ).to_dict()

        self._stats["calls"] += 1
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                async with self._mcp_semaphore:
                    result = await self._execute_mcp_call(tool_name, arguments, timeout)

                # Éxito -> resetear circuit breaker
                self._circuit_breaker.record_success()
                return result

            except Exception as e:
                last_error = _classify_error(e, tool_name)
                self._stats["errors"] += 1

                if not last_error.retryable or attempt >= max_retries:
                    self._circuit_breaker.record_failure()
                    logger.error(f"❌ MCP [{tool_name}] fallo definitivo: {last_error.message}")
                    return last_error.to_dict()

                # Backoff exponencial con jitter
                self._stats["retries"] += 1
                wait = min(2 ** attempt + random.uniform(0.5, 1.5), 15.0)
                logger.warning(f"⚠️ MCP [{tool_name}] intento {attempt+1}/{max_retries+1} falló. Retry en {wait:.1f}s...")
                await asyncio.sleep(wait)

        return (last_error or MCPError(MCPErrorType.INTERNAL, "Error inesperado.", tool_name)).to_dict()

    async def _execute_mcp_call(self, tool_name: str, arguments: dict, timeout: float) -> dict:
        """Ejecuta una llamada individual al proceso MCP."""
        logger.debug(f"MCP -> {tool_name} | Args: {str(arguments)[:100]}...")
        t0 = time.time()

        env_vars = os.environ.copy()
        server_params = StdioServerParameters(
            command=self._mcp_exe, args=[], env=env_vars,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=30.0)
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments),
                    timeout=timeout
                )
                elapsed = time.time() - t0
                logger.debug(f"MCP <- {tool_name} completado en {elapsed:.1f}s")
                return self._parse_mcp_result(result)

    def _parse_mcp_result(self, result: Any) -> dict:
        """
        Parsea el resultado del MCP de forma segura y defensiva utilizando parámetros getattr.
        """
        if result is None:
            return {"error": "El servidor MCP no retornó ninguna respuesta (None)"}

        # Manejo nativo de error según la estructura de tools en el modelo
        if getattr(result, 'isError', False):
            error_components = []
            content_list = getattr(result, 'content', [])
            for item in content_list:
                text_val = getattr(item, 'text', '')
                if text_val:
                    error_components.append(text_val)
            
            return {"error": " ".join(error_components) or "Error interno en el servidor MCP"}

        # Priorizar structuredContent si existe
        struct_data = getattr(result, 'structuredContent', None)
        if struct_data:
            return struct_data

        # Extraer contenido de texto plano
        extracted_text = []
        content_list = getattr(result, 'content', [])
        
        for item in content_list:
            text_val = getattr(item, 'text', None)
            if text_val:
                extracted_text.append(text_val)

        combined = "\n".join(extracted_text)

        # Tratar de decodificar en caso de que sea JSON encapsulado en texto
        if combined:
            try:
                return json.loads(combined)
            except json.JSONDecodeError:
                return {"text": combined}
        
        return {"text": str(result)}

    # ──────────────────────────────────────────────────────────
    # LIBRERÍA LOCAL (CACHE DE NOTEBOOKS)
    # ──────────────────────────────────────────────────────────

    def _load_local_library(self) -> None:
        """Carga el index local si está disponible de forma segura."""
        if LIBRARY_PATH.is_file():
            try:
                data = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
                notebooks = data.get("notebooks", [])

                if isinstance(notebooks, list):
                    iterator_items = [(nb.get("id", nb.get("notebook_id", "")), nb) for nb in notebooks if isinstance(nb, dict)]
                elif isinstance(notebooks, dict):
                    iterator_items = notebooks.items()
                else:
                    iterator_items = []

                for nb_id, nb_data in iterator_items:
                    if nb_id and isinstance(nb_data, dict):
                        self._cache[nb_id] = NotebookEntry(
                            notebook_id=nb_id,
                            title=nb_data.get("title", ""),
                            tags=nb_data.get("tags", []),
                            source_count=len(nb_data.get("sources", []))
                        )

                self._cache_ts = time.time()
                logger.info(f"Caché local sincronizado: {len(self._cache)} cuadernos.")

            except json.JSONDecodeError as e:
                logger.error(f"Librería local corrupta: {e}")
            except Exception as e:
                logger.warning(f"Error cargando index local: {e}")

    def _invalidate_cache(self) -> None:
        """Invalida el caché forzando recarga en la próxima consulta."""
        self._cache_ts = 0.0
        logger.debug("Caché invalidado por mutación.")

    def _is_cache_fresh(self) -> bool:
        """Verifica si el caché sigue vigente dentro del TTL."""
        return self._cache_ts > 0 and (time.time() - self._cache_ts) < self._cache_ttl

    # ──────────────────────────────────────────────────────────
    # OPERACIONES BÁSICAS MEJORADAS
    # ──────────────────────────────────────────────────────────

    async def list_notebooks(self) -> dict:
        """Lista todos los cuadernos. Actualiza caché al éxito."""
        result = await self._call_mcp("notebook_list", {})
        if isinstance(result, dict) and "error" not in result:
            self._cache_ts = time.time()
        return result

    async def create_notebook(self, title: str) -> dict:
        """Crea un cuaderno e invalida caché."""
        result = await self._call_mcp("notebook_create", {"title": title})
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        logger.info(f"📓 Cuaderno creado: {title}")
        return result

    async def get_notebook(self, notebook_id: str) -> dict:
        """Obtiene metadata de un cuaderno específico."""
        return await self._call_mcp("notebook_get", {"notebook_id": notebook_id})

    async def query_notebook(
        self, notebook_id: str, query: str,
        source_format: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> dict:
        """
        Consulta un cuaderno con soporte de citaciones y sesiones multi-turno.

        Args:
            notebook_id: ID del cuaderno
            query: Pregunta a realizar
            source_format: Formato de citas (ignorado en esta versión del MCP)
            session_id: ID de sesión para conversaciones multi-turno
        """
        args = {"notebook_id": notebook_id, "query": query}

        # Sesiones multi-turno: reutilizar sesión existente mapeada a conversation_id
        sid = session_id or self._sessions.get(notebook_id)
        if sid:
            args["conversation_id"] = sid

        result = await self._call_mcp("notebook_query", args)

        # Guardar conversation_id retornado para conversaciones encadenadas
        if isinstance(result, dict):
            new_sid = result.get("conversation_id") or result.get("session_id")
            if new_sid:
                self._sessions[notebook_id] = new_sid

        return result

    async def describe_notebook(self, notebook_id: str) -> dict:
        """Obtiene descripción detallada de un cuaderno."""
        return await self._call_mcp("notebook_describe", {"notebook_id": notebook_id})

    # ──────────────────────────────────────────────────────────
    # SISTEMA DE ETIQUETAS
    # ──────────────────────────────────────────────────────────

    async def tag_notebook(self, notebook_id: str, tags: str) -> dict:
        tag_parts = [t.strip() for t in tags.split(",") if t.strip()]

        # Filtramos para tener la etiqueta líder de área (puede ser #legal- o #juris-)
        area_tag = next(
            (t for t in tag_parts if (t.startswith("#legal-") or t.startswith("#juris-"))),
            next((t for t in tag_parts if t in [TAG_LEGAL_ROOT, TAG_JURIS_ROOT]), TAG_LEGAL_ROOT)
        )

        nb_info = await self.get_notebook(notebook_id)
        if isinstance(nb_info, dict) and "error" in nb_info:
            return nb_info

        current_title = nb_info.get("title", nb_info.get("notebook", {}).get("title", ""))

        if current_title and f"[{area_tag}]" in current_title:
            return {"status": "already_tagged", "title": current_title}

        import re
        clean_title = re.sub(r'\[#legal[^\]]*\]\s*', '', current_title).strip()
        new_title = f"[{area_tag}] {clean_title}" if clean_title else current_title

        result = await self._call_mcp("notebook_rename", {
            "notebook_id": notebook_id,
            "new_title": new_title
        })
        logger.info(f"🏷️ Etiqueta [{area_tag}] vinculada a cuaderno {notebook_id[:8]}")
        return result

    async def search_by_tag(self, tag: str) -> dict:
        """Busca cuadernos por etiqueta en el título."""
        all_notebooks = await self.list_notebooks()
        if isinstance(all_notebooks, dict) and "error" in all_notebooks:
            return all_notebooks

        notebooks_list = all_notebooks.get("notebooks", [])

        matching = [
            nb for nb in notebooks_list
            if isinstance(nb, dict) and
            ((tag == TAG_LEGAL_ROOT and "[#legal" in nb.get("title", "")) or
             (tag == TAG_JURIS_ROOT and "[#juris" in nb.get("title", "")) or
             (f"[{tag}]" in nb.get("title", "")))
        ]

        return {"status": "success", "tag": tag, "count": len(matching), "notebooks": matching}

    async def batch_query(
        self, query: str, tags: str,
        max_concurrent: int = 3,
        source_format: Optional[str] = None
    ) -> dict:
        """
        Consulta CONCURRENTE REAL a múltiples cuadernos con semáforo.
        Antes limitaba a 1 cuaderno; ahora procesa hasta max_concurrent en paralelo.
        """
        tagged = await self.search_by_tag(tags)
        if isinstance(tagged, dict) and "error" in tagged:
            return tagged

        notebooks = tagged.get("notebooks", [])
        if not notebooks:
            return {
                "status": "no_notebooks", "tag": tags,
                "message": f"No hay cuadernos bajo la etiqueta '{tags}'."
            }

        # Limitar a 5 notebooks máximo para no agotar recursos
        targets = notebooks[:5]
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _query_one(nb: dict) -> Optional[dict]:
            nb_id = nb.get("id", "")
            if not nb_id:
                return None
            async with semaphore:
                try:
                    res = await self.query_notebook(nb_id, query, source_format=source_format)
                    return {"notebook_id": nb_id, "title": nb.get("title", ""), "response": res}
                except Exception as e:
                    logger.error(f"Error batch_query cuaderno {nb_id}: {e}")
                    return {"notebook_id": nb_id, "title": nb.get("title", ""), "response": {"error": str(e)}}

        tasks = [_query_one(nb) for nb in targets]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        clean_results = [r for r in results if r is not None]

        return {
            "status": "success", "tag": tags, "query": query,
            "notebooks_queried": len(clean_results),
            "results": clean_results
        }

    # ──────────────────────────────────────────────────────────
    # FUENTES / INVESTIGACIÓN / NOTAS
    # ──────────────────────────────────────────────────────────

    async def add_url_source(self, notebook_id: str, url: str) -> dict:
        """Añade una URL como fuente e invalida caché."""
        result = await self._call_mcp("notebook_add_url", {"notebook_id": notebook_id, "url": url})
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        return result

    async def add_text_source(self, notebook_id: str, text: str, title: str) -> dict:
        """Añade texto como fuente e invalida caché."""
        result = await self._call_mcp("notebook_add_text", {"notebook_id": notebook_id, "text": text, "title": title})
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        return result

    async def start_research(self, notebook_id: str, query: str, source: str = "web", mode: str = "fast") -> dict:
        """Inicia investigación web sobre un tema en un cuaderno."""
        return await self._call_mcp("research_start", {"notebook_id": notebook_id, "query": query, "source": source, "mode": mode})

    async def research_status(self, notebook_id: str) -> dict:
        """Consulta el estado de una investigación en curso."""
        return await self._call_mcp("research_status", {"notebook_id": notebook_id})

    async def research_import(self, notebook_id: str, task_id: str) -> dict:
        """Importa resultados de investigación al cuaderno."""
        return await self._call_mcp("research_import", {"notebook_id": notebook_id, "task_id": task_id})

    async def describe_source(self, source_id: str) -> dict:
        """Obtiene un resumen generado por IA y palabras clave de una fuente."""
        return await self._call_mcp("source_describe", {"source_id": source_id})

    async def get_source_content(self, source_id: str) -> dict:
        """Obtiene el texto crudo original de una fuente sin procesamiento de IA."""
        return await self._call_mcp("source_get_content", {"source_id": source_id})

    async def add_drive_source(self, notebook_id: str, document_id: str, title: str, doc_type: str = "doc") -> dict:
        """Añade un documento de Google Drive como fuente e invalida el caché."""
        result = await self._call_mcp("notebook_add_drive", {
            "notebook_id": notebook_id,
            "document_id": document_id,
            "title": title,
            "doc_type": doc_type
        })
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        return result

    async def delete_notebook(self, notebook_id: str, confirm: bool = True) -> dict:
        """Elimina un cuaderno permanentemente e invalida el caché."""
        result = await self._call_mcp("notebook_delete", {"notebook_id": notebook_id, "confirm": confirm})
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        return result

    async def delete_source(self, source_id: str, confirm: bool = True) -> dict:
        """Elimina una fuente permanentemente de un cuaderno e invalida el caché."""
        result = await self._call_mcp("source_delete", {"source_id": source_id, "confirm": confirm})
        if isinstance(result, dict) and "error" not in result:
            self._invalidate_cache()
        return result

    async def create_report(
        self,
        notebook_id: str,
        source_ids: Optional[List[str]] = None,
        report_format: str = "Briefing Doc",
        custom_prompt: str = "",
        language: str = "es",
        confirm: bool = True
    ) -> dict:
        """Genera un informe estructurado (memorial, guía, etc.) a partir de las fuentes del cuaderno."""
        return await self._call_mcp("report_create", {
            "notebook_id": notebook_id,
            "source_ids": source_ids,
            "report_format": report_format,
            "custom_prompt": custom_prompt,
            "language": language,
            "confirm": confirm
        })

    async def create_note(self, notebook_id: str, title: str, content: str = "") -> dict:
        """Crea una nota en un cuaderno. (Nota: no soportado en esta versión del MCP)"""
        logger.warning("La creación de notas independientes no está soportada por el servidor MCP actual.")
        return {"error": "La creación de notas independientes no está soportada en esta versión del MCP."}

    async def update_note(self, notebook_id: str, note_id: str, title: str, content: str) -> dict:
        """Actualiza una nota existente. (Nota: no soportado en esta versión del MCP)"""
        logger.warning("La edición de notas no está soportada por el servidor MCP actual.")
        return {"error": "La edición de notas no está soportada en esta versión del MCP."}

    # ──────────────────────────────────────────────────────────
    # SESIONES MULTI-TURNO
    # ──────────────────────────────────────────────────────────

    def get_session_id(self, notebook_id: str) -> Optional[str]:
        """Obtiene el session_id activo para un notebook."""
        return self._sessions.get(notebook_id)

    def clear_session(self, notebook_id: str) -> None:
        """Limpia la sesión de un notebook para empezar conversación nueva."""
        self._sessions.pop(notebook_id, None)
        logger.debug(f"Sesión limpiada para notebook {notebook_id[:8]}")

    def clear_all_sessions(self) -> None:
        """Limpia todas las sesiones activas."""
        count = len(self._sessions)
        self._sessions.clear()
        logger.info(f"🧹 {count} sesiones limpiadas.")

    # ──────────────────────────────────────────────────────────
    # WORKFLOWS ORQUESTADOS
    # ──────────────────────────────────────────────────────────

    async def create_legal_notebook(self, titulo: str, area_legal: str, fuentes_urls: Optional[List[str]] = None) -> dict:
        """
        Crea el cuaderno jurídico, lo etiqueta e indexa todas las urls suministradas (En paralelo).
        """
        tag_area = JURIS_TAGS.get(area_legal, LEGAL_TAGS.get(area_legal, f"#legal-{area_legal}"))
        tag_root = TAG_JURIS_ROOT if area_legal in JURIS_TAGS else TAG_LEGAL_ROOT
        full_title = f"[{tag_area}] {titulo}"

        create_result = await self.create_notebook(full_title)
        if isinstance(create_result, dict) and "error" in create_result:
            return create_result

        notebook_id = create_result.get("notebook_id", create_result.get("id", create_result.get("notebookId", "")))
        if not notebook_id:
            notebook_id = create_result.get("notebook", {}).get("id", "")

        if not notebook_id:
            return {"error": "Error interno determinando ID del cuaderno creado", "raw_data": str(create_result)[:500]}

        await self.tag_notebook(notebook_id, f"{tag_root},{tag_area}")

        # Subida secuencial de URLs para no colapsar los procesos MCP
        sources_added = []
        if fuentes_urls:
            for url in fuentes_urls:
                try:
                    res = await self.add_url_source(notebook_id, url)
                    is_err = isinstance(res, dict) and "error" in res
                    sources_added.append({"url": url, "status": "error" if is_err else "ok"})
                except Exception as e:
                    sources_added.append({"url": url, "status": f"error: {str(e)}"})

        return {
            "status": "success",
            "notebook_id": notebook_id,
            "title": full_title,
            "tags": [tag_root, tag_area],
            "sources_added": sources_added,
            "message": f"Construido 🏛️ '{full_title}' correctamente."
        }

    async def query_legal(
        self, query: str,
        area_legal: Optional[str] = None,
        notebook_id: Optional[str] = None,
        category: str = "legal",
        source_format: Optional[str] = None
    ) -> dict:
        """
        Consulta la base jurídica. Category puede ser 'legal' (leyes) o 'juris' (sentencias).
        """
        if notebook_id:
            result = await self.query_notebook(notebook_id, query, source_format=source_format)
            return {"source": "notebook_direct", "notebook_id": notebook_id, "query": query, "response": result}

        # Selección de etiqueta base según categoría
        if category == "juris":
            tag = JURIS_TAGS.get(area_legal, TAG_JURIS_ROOT) if area_legal else TAG_JURIS_ROOT
        else:
            tag = LEGAL_TAGS.get(area_legal, TAG_LEGAL_ROOT) if area_legal else TAG_LEGAL_ROOT

        result = await self.batch_query(query, tag, source_format=source_format)
        return {"source": "batch_query", "tag": tag, "category": category, "query": query, "response": result}

    async def research_legal(self, tema: str, area_legal: str = "constitucional", modo: str = "fast") -> dict:
        titulo = f"Research: {tema[:45]} - {datetime.now().strftime('%Y-%m-%d')}"
        create_result = await self.create_legal_notebook(titulo, area_legal)
        if isinstance(create_result, dict) and "error" in create_result:
            return create_result

        notebook_id = create_result.get("notebook_id", "")
        research_result = await self.start_research(notebook_id=notebook_id, query=tema, source="web", mode=modo)

        return {
            "status": "research_started",
            "notebook_id": notebook_id,
            "title": create_result.get("title", ""),
            "tags": create_result.get("tags", []),
            "research": research_result,
            "message": f"Investigación '{modo}' disparada correctamente."
        }

    async def _search_web(self, query: str, count: int = 10) -> List[dict]:
        """Realiza una búsqueda web a través de la API de Brave."""
        brave_api_key = os.getenv("BRAVE_API_KEY")
        if not brave_api_key:
            logger.warning("BRAVE_API_KEY no configurada en variables de entorno.")
            return []
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": brave_api_key
                    },
                    params={
                        "q": query,
                        "count": count
                    },
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                web_results = data.get("web", {}).get("results", [])
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "description": r.get("description", "")
                    }
                    for r in web_results
                ]
        except Exception as e:
            logger.error(f"Error en _search_web de NotebookLMService: {e}")
            return []

    async def ingest_jurisprudencia(
        self,
        referencia: str,
        area_legal: str = "constitucional",
        notebook_id: Optional[str] = None,
        deep_research: bool = False,
        max_sources: int = 5
    ) -> dict:
        """
        Orquesta la ingesta automatizada de jurisprudencia colombiana:
        1. Busca la referencia en Brave Search filtrando por site:.gov.co o dominios de autoridad.
        2. Filtra y rankea las URLs obtenidas.
        3. Crea cuaderno si no existe.
        4. Ingesta las URLs más relevantes.
        5. Lanza deep research si se solicita.
        """
        query = f'"{referencia}" site:gov.co'
        results = await self._search_web(query, count=15)
        
        if not results:
            query_fallback = referencia
            results = await self._search_web(query_fallback, count=15)

        dominios_autoridad = [
            "corteconstitucional.gov.co",
            "cortesuprema.gov.co",
            "consejodeestado.gov.co",
            "suin-juriscol.gov.co",
            "secretariasenado.gov.co",
            "funcionpublica.gov.co",
            "minhacienda.gov.co",
            "mintrabajo.gov.co",
            "alcaldiabogota.gov.co"
        ]

        ranked_results = []
        for r in results:
            url = r.get("url", "").lower()
            score = 0
            for idx, domain in enumerate(dominios_autoridad):
                if domain in url:
                    score = 100 - idx
                    break
            if not score:
                if ".gov.co" in url:
                    score = 50
                elif ".edu.co" in url or "ambitojuridico.com" in url or "legis.com.co" in url:
                    score = 30
                else:
                    score = 10
            
            if "sentencia" in url or "relatoria" in url or "providencia" in url:
                score += 5
            
            ranked_results.append((score, r))

        ranked_results.sort(key=lambda x: x[0], reverse=True)
        top_sources = [item[1] for item in ranked_results if item[0] >= 10][:max_sources]

        if not top_sources:
            return {"error": f"No se encontraron fuentes confiables de jurisprudencia para la referencia: {referencia}."}

        if not notebook_id:
            titulo = f"Jurisprudencia: {referencia}"
            create_res = await self.create_legal_notebook(titulo, area_legal)
            if isinstance(create_res, dict) and "error" in create_res:
                return create_res
            notebook_id = create_res.get("notebook_id")

        if not notebook_id:
            return {"error": "No se pudo obtener o crear el cuaderno para ingestar la jurisprudencia."}

        sources_added = []
        for src in top_sources:
            url = src["url"]
            title = src["title"]
            try:
                res = await self.add_url_source(notebook_id, url)
                if isinstance(res, dict) and "error" in res:
                    sources_added.append({"title": title, "url": url, "status": "error", "message": res["error"]})
                else:
                    sources_added.append({"title": title, "url": url, "status": "ok"})
            except Exception as e:
                sources_added.append({"title": title, "url": url, "status": "error", "message": str(e)})

        research_status = None
        if deep_research:
            try:
                research_status = await self.start_research(notebook_id, query=referencia, source="web", mode="deep")
            except Exception as e:
                logger.error(f"Error iniciando deep research para {referencia}: {e}")
                research_status = {"error": str(e)}

        return {
            "status": "success",
            "notebook_id": notebook_id,
            "referencia": referencia,
            "sources_attempted": len(top_sources),
            "sources_added": sources_added,
            "deep_research_started": deep_research,
            "research_status": research_status
        }

    async def build_linea_jurisprudencial(
        self,
        tema: str,
        notebook_id: Optional[str] = None,
        corte: str = "todas",
        generar_reporte: bool = True
    ) -> dict:
        """
        Analiza el corpus de jurisprudencia en el cuaderno y construye un análisis de precedente.
        """
        prompt = f"""
Analiza TODAS las sentencias y fuentes disponibles sobre el tema: "{tema}".

Estructura tu respuesta EXACTAMENTE en las siguientes secciones en español:

## 1. SENTENCIA HITO (Leading Case)
- Identifica la sentencia fundacional o líder que estableció el precedente sobre este tema.
- Incluye: radicado (ej: T-760/2008), magistrado ponente, hechos clave y la decisión adoptada.

## 2. LÍNEA CONFIRMATORIA
- Lista sentencias posteriores que RATIFICARON y consolidaron el precedente.
- Para cada una: radicado, año, aporte específico.

## 3. LÍNEA MODIFICATORIA O DISIDENTE
- Lista sentencias que CAMBIARON, MATIZARON, LIMITARON o CONTRADIJERON el criterio.
- Explica detalladamente en qué difieren del precedente original.

## 4. RATIO DECIDENDI VIGENTE
- Extrae la REGLA DE DECISIÓN actual aplicada por la corte, citando textualmente.
- Indica los requisitos o subreglas que la componen.

## 5. OBITER DICTA RELEVANTES
- Argumentos complementarios no vinculantes pero informativos.

## 6. ESTADO ACTUAL DEL PRECEDENTE
- ¿Sigue vigente hoy en día? ¿Fue superado por una sentencia de unificación (SU) o ley posterior?
- Indica el radicado y la fecha de la última sentencia que lo reiteró.

IMPORTANTE: Cita SIEMPRE el número de sentencia y año. No inventes referencias.
"""
        target_notebook_id = notebook_id
        
        if not target_notebook_id:
            tag = TAG_JURIS_ROOT if corte == "todas" else JURIS_TAGS.get(corte, TAG_JURIS_ROOT)
            query_res = await self.batch_query(query=prompt, tags=tag)
        else:
            query_res = await self.query_notebook(notebook_id=target_notebook_id, query=prompt)

        report_res = None
        if generar_reporte and target_notebook_id:
            try:
                custom_prompt = (
                    f"Genera un análisis formal de línea jurisprudencial sobre: {tema}. "
                    "Usa formato académico colombiano con la siguiente estructura: "
                    "Sentencia Hito → Línea Confirmatoria → Línea Modificatoria o Disidente → "
                    "Ratio Decidendi Vigente → Estado Actual. "
                    "Incluye una tabla cronológica de sentencias con su radicado y aporte principal."
                )
                report_res = await self.create_report(
                    notebook_id=target_notebook_id,
                    report_format="Create Your Own",
                    custom_prompt=custom_prompt,
                    language="es",
                    confirm=True
                )
            except Exception as e:
                logger.error(f"Error generando reporte de línea jurisprudencial: {e}")
                report_res = {"error": str(e)}

        return {
            "status": "success",
            "tema": tema,
            "notebook_id": target_notebook_id,
            "corte": corte,
            "linea_jurisprudencial": query_res,
            "reporte_generado": report_res
        }

    async def red_team_legal(
        self,
        texto: Optional[str] = None,
        document_id: Optional[int] = None,
        file_path: Optional[str] = None,
        nivel_profundidad: str = "standard",
        area_legal: str = "constitucional"
    ) -> dict:
        """
        Auditoría adversarial de un escrito jurídico contra NotebookLM.
        """
        escrito_texto = ""
        if texto:
            escrito_texto = texto
        elif file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    escrito_texto = f.read()
            except Exception as e:
                logger.error(f"Error leyendo file_path en red_team_legal: {e}")

        if not escrito_texto:
            return {"error": "No se proporcionó ningún escrito o texto válido para auditar."}

        # Extracción simple de referencias usando regex
        regex_sentencias = r'\b([C|T|SU|A]-[0-9]+(?:\/[0-9]+| de [0-9]+))\b'
        regex_leyes = r'\b(Ley \d+(?: de \d+)?|Decreto \d+(?: de \d+)?|Código de Comercio|Código Civil)\b'
        
        sentencias_encontradas = re.findall(regex_sentencias, escrito_texto, re.IGNORECASE)
        leyes_encontradas = re.findall(regex_leyes, escrito_texto, re.IGNORECASE)
        referencias = list(set(sentencias_encontradas + leyes_encontradas))
        
        vigencia_resultados = {}
        tag_busqueda = JURIS_TAGS.get(area_legal, LEGAL_TAGS.get(area_legal, TAG_LEGAL_ROOT))
        
        if referencias and nivel_profundidad in ["standard", "exhaustivo"]:
            ref_str = ", ".join(referencias[:10])
            prompt_vigencia = f"""
Para cada una de las siguientes normas y sentencias colombianas, indica utilizando la base de conocimiento:
1. ¿Sigue VIGENTE actualmente?
2. ¿Ha sido MODIFICADA, declarada INEXEQUIBLE o derogada en todo o en parte? ¿Por qué sentencia o ley?
3. ¿Cuál es el criterio/regla principal que establece?

Referencias a validar: {ref_str}
"""
            vigencia_resultados = await self.batch_query(query=prompt_vigencia, tags=tag_busqueda)

        prompt_adversarial = f"""
Actúa como el abogado MÁS EXPERTO y adversarial de la CONTRAPARTE. Lee el siguiente escrito jurídico y realiza un análisis crítico y de vulnerabilidades detallado:

1. VACÍOS ARGUMENTATIVOS: ¿Qué argumentos o excepciones importantes faltaron en el escrito?
2. DEBILIDADES JURÍDICAS: ¿Dónde es más vulnerable y atacable este escrito?
3. CONTRAARGUMENTOS: ¿Qué argumentos y defensas presentarías para refutarlo?
4. NORMAS OMITIDAS: ¿Hay normas o sentencias colombianas vigentes y relevantes que no fueron citadas y benefician a la contraparte?
5. ERRORES DE FUNDAMENTACIÓN: ¿Alguna de las normas o sentencias citadas está derogada, modificada o mal aplicada al caso?

FUNDAMENTA cada punto con la norma o sentencia colombiana aplicable. No inventes referencias.

ESCRITO A ANALIZAR:
{escrito_texto[:15000]}
"""
        analisis_adversarial = await self.batch_query(query=prompt_adversarial, tags=tag_busqueda)

        sugerencias_fortalecimiento = {}
        if nivel_profundidad == "exhaustivo":
            prompt_sugerencias = f"""
Basándote en el análisis adversarial anterior, genera SUGERENCIAS CONCRETAS Y ACCIONABLES de fortalecimiento y mejora para el escrito:

1. Citas de normas y sentencias específicas que deberían agregarse para blindar la argumentación.
2. Argumentos preventivos para responder a los posibles ataques de la contraparte.
3. Reformulaciones sugeridas de párrafos que presenten debilidades.

ESCRITO A ANALIZAR:
{escrito_texto[:15000]}
"""
            sugerencias_fortalecimiento = await self.batch_query(query=prompt_sugerencias, tags=tag_busqueda)

        return {
            "status": "success",
            "nivel_profundidad": nivel_profundidad,
            "referencias_detectadas": referencias,
            "vigencia_analisis": vigencia_resultados,
            "analisis_adversarial": analisis_adversarial,
            "sugerencias_fortalecimiento": sugerencias_fortalecimiento if nivel_profundidad == "exhaustivo" else None
        }

    def get_available_areas(self) -> dict:
        """Retorna la taxonomía de áreas jurídicas disponibles."""
        return {
            "areas": LEGAL_TAGS,
            "juris_areas": JURIS_TAGS,
            "root_tag": TAG_LEGAL_ROOT,
            "juris_root_tag": TAG_JURIS_ROOT,
            "description": "Áreas jurídicas vigentes para etiquetado"
        }

    def get_status(self) -> dict:
        """Retorna estado completo del servicio con métricas."""
        return {
            "version": "2.0",
            "mcp_exe": self._mcp_exe or "NO ENCONTRADO",
            "mcp_sdk": "OK" if MCP_SDK_AVAILABLE else "NO INSTALADO",
            "cached_notebooks": len(self._cache),
            "cache_fresh": self._is_cache_fresh(),
            "cache_age_seconds": int(time.time() - self._cache_ts) if self._cache_ts > 0 else -1,
            "circuit_breaker": self._circuit_breaker.state,
            "active_sessions": len(self._sessions),
            "default_source_format": self.default_source_format,
            "available_tags": LEGAL_TAGS,
            "library_path": str(LIBRARY_PATH),
            "library_exists": LIBRARY_PATH.is_file(),
            "stats": self._stats.copy()
        }

    async def check_health(self) -> dict:
        """
        Health check proactivo: verifica conectividad y autenticación MCP.
        Útil para diagnóstico antes de operaciones pesadas.
        """
        status = self.get_status()
        health = {"healthy": False, **status}

        if not self._mcp_exe:
            health["diagnosis"] = "notebooklm-mcp no instalado. Ejecuta: uv tool install notebooklm-mcp"
            return health
        if not MCP_SDK_AVAILABLE:
            health["diagnosis"] = "SDK MCP no instalado. Ejecuta: pip install mcp"
            return health

        try:
            # Usamos notebook_list como prueba de vida (existe en todos los MCPs de NotebookLM)
            result = await self._call_mcp("notebook_list", {}, timeout=15.0, max_retries=0)
            if isinstance(result, dict) and "error" not in result:
                health["healthy"] = True
                health["mcp_health"] = {"status": "connected", "notebooks_count": len(result.get("notebooks", []))}
                health["diagnosis"] = "Servicio operativo y conectado al MCP."
            else:
                health["diagnosis"] = f"MCP respondió con error: {result.get('error', 'desconocido')}"
        except Exception as e:
            health["diagnosis"] = f"Error de conectividad: {str(e)}"

        return health

    def get_metrics(self) -> dict:
        """Retorna métricas de rendimiento del servicio."""
        return {
            "total_calls": self._stats["calls"],
            "total_errors": self._stats["errors"],
            "total_retries": self._stats["retries"],
            "cache_hits": self._stats["cache_hits"],
            "error_rate": f"{(self._stats['errors'] / max(self._stats['calls'], 1)) * 100:.1f}%",
            "circuit_breaker_state": self._circuit_breaker.state,
            "active_sessions": len(self._sessions)
        }


# Instancia global Singleton pre-configurada
notebooklm_service = NotebookLMService()