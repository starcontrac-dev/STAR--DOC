import logging
import random
import asyncio
import time
import httpx
from typing import List, Optional, Any, Dict
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)

# 🔒 SEGURIDAD: Silenciar logs de httpx a nivel WARNING.
# httpx registra las URLs completas a nivel INFO, incluyendo parámetros de query
# como ?key=AIzaSy..., exponiendo las API keys de Gemini en texto plano en la terminal.
logging.getLogger("httpx").setLevel(logging.WARNING)



class CircuitState(Enum):
    """Estados del Circuit Breaker."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit Breaker para prevenir requests a modelos degradados.
    Estados: CLOSED → OPEN → HALF_OPEN → CLOSED
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 120):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: float = 0

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"🔴 Circuit Breaker abierto después de {self.failures} fallos")

    def record_success(self):
        self.failures = 0
        self.state = CircuitState.CLOSED

    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("🟡 Circuit Breaker en HALF_OPEN (probando recuperación)")
                return True
            return False
        return True  # HALF_OPEN permite un intento


class AIService:
    """
    Servicio Singleton de Alta Disponibilidad para Gemini 2026.
    
    Mejoras Implementadas (Roadmap Completo):
    - FASE 1.1: Context Caching Automático (implicit caching optimizado)
    - FASE 1.3: Métricas avanzadas (latencia, costos, throughput)
    - FASE 2.1: Soporte para Code Execution
    - FASE 2.3: Grounding Automático Inteligente
    - FASE 3.1: Circuit Breaker Pattern
    - FASE 3.3: Health Checker Proactivo
    """
    _instance: Optional['AIService'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Obtener API keys de variables de entorno
        self.api_keys: List[str] = self._load_api_keys()
        if not self.api_keys:
            raise ValueError("GEMINI_API_KEYS no configuradas.")

        # Almacén de claves identificadas como inválidas permanentemente (evita error 400 repetitivo)
        self.invalid_keys = set()

        # Jerarquía de modelos para asegurar disponibilidad (Gemini 2026)
        # Prioridad: Flash 2.5 -> Flash-Lite 2.5 -> Pro 2.5
        self.models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.5-pro"
        ]

        # Estado de cooldown para claves agotadas: "key_index:model_name" -> timestamp
        self.exhausted_keys: Dict[str, float] = {}

        # FASE 3.1: Circuit Breaker por modelo
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            model: CircuitBreaker(failure_threshold=5, recovery_timeout=120)
            for model in self.models
        }

        # FASE 1.3: Métricas avanzadas por modelo
        self.model_stats: Dict[str, Dict[str, Any]] = {
            model: {
                "success": 0,
                "failure": 0,
                "total": 0,
                "total_latency_ms": 0.0,
                "total_tokens_estimated": 0,
            }
            for model in self.models
        }

        # FASE 1.3: Métricas globales
        self.request_history: List[Dict[str, Any]] = []
        self.max_history = 1000  # Mantener últimos 1000 requests para métricas
        self.context_caches: Dict[str, Dict[str, Any]] = {}

        # FASE 2.3: Keywords para grounding automático
        self.grounding_keywords = [
            "ley", "decreto", "sentencia", "resolución", "norma", "corte constitucional",
            "congreso", "jurisprudencia", "actual", "reciente", "nuevo", "cambio",
            "2025", "2026", "último", "modifica", "reforma", "vigente", "deroga"
        ]

        # FASE 3.3: Estado de health checker
        self.model_health: Dict[str, str] = {model: "unknown" for model in self.models}
        self._health_checker_task: Optional[asyncio.Task] = None

        # httpx AsyncClient reutilizable con connection pooling
        self._http_client: Optional[httpx.AsyncClient] = None

        # Token para iniciar health checker solo una vez
        self._health_checker_started = False

        self._initialized = True
        logger.info(
            f"AIService Elite inicializado. Modelos: {self.models}, "
            f"Keys: {len(self.api_keys)}, Circuit Breakers: {len(self.circuit_breakers)}"
        )

    def _load_api_keys(self) -> List[str]:
        """Carga todas las API keys de Gemini desde variables de entorno."""
        import os
        keys = []

        # Primary key
        primary = os.getenv("GEMINI_API_KEY")
        if primary and "your_gemini" not in primary.lower():
            keys.append(primary)

        # Additional keys (GEMINI_API_KEY_2, GEMINI_API_KEY_3, etc.)
        for i in range(2, 11):
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if key and "your_gemini" not in key.lower():
                keys.append(key)

        return keys

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente httpx con configuración optimizada."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client

    async def close(self):
        """Cierra el cliente httpx y health checker al shutdown."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
        
        if self._health_checker_task and not self._health_checker_task.done():
            self._health_checker_task.cancel()
            try:
                await self._health_checker_task
            except asyncio.CancelledError:
                pass

    async def _get_key_status(self, idx: int, model: str) -> bool:
        """Verifica si una combinación de clave y modelo está disponible."""
        # 0. Si la clave ha sido marcada como inválida en tiempo de ejecución, ignorarla de inmediato
        if idx in self.invalid_keys:
            return False

        # 1. Intentar validar en Redis
        try:
            from app.services.redis_circuit_breaker import RedisCircuitBreaker
            if not await RedisCircuitBreaker.is_key_available(idx, model):
                return False
        except Exception as e:
            logger.warning(f"Error al verificar key status en Redis (degradación activa): {e}")

        # 2. Fallback / Sincronización en memoria
        status_key = f"{idx}:{model}"
        now = time.time()
        if status_key in self.exhausted_keys:
            # 60 segundos de cooldown para claves con 429
            if now - self.exhausted_keys[status_key] < 60:
                return False
            del self.exhausted_keys[status_key]
        return True

    def _estimate_tokens(self, text: str) -> int:
        """Estima el número de tokens (~4 caracteres por token en promedio)."""
        return len(text) // 4

    def _deduplicate_tools(self, payload: dict) -> None:
        """Deduplica de manera absoluta todas las declaraciones de funciones en el payload para evitar errores en Gemini."""
        if "tools" in payload and isinstance(payload["tools"], list):
            all_seen_names = set()
            for tool_obj in payload["tools"]:
                if "function_declarations" in tool_obj:
                    unique_funcs = []
                    for func in tool_obj["function_declarations"]:
                        name = func.get("name")
                        if name not in all_seen_names:
                            all_seen_names.add(name)
                            unique_funcs.append(func)
                    tool_obj["function_declarations"] = unique_funcs
            
            # Remover objetos function_declarations vacíos
            payload["tools"] = [
                t for t in payload["tools"] 
                if not ("function_declarations" in t and len(t["function_declarations"]) == 0)
            ]

    def _record_request(self, model: str, latency_ms: float, tokens_in: int, tokens_out: int, success: bool):
        """Registra métricas de un request para análisis posterior."""
        self.model_stats[model]["total_latency_ms"] += latency_ms
        self.model_stats[model]["total_tokens_estimated"] += tokens_in + tokens_out
        
        # Mantener historial reciente
        self.request_history.append({
            "model": model,
            "latency_ms": latency_ms,
            "tokens": tokens_in + tokens_out,
            "success": success,
            "timestamp": time.time()
        })
        
        # Trim historial si excede máximo
        if len(self.request_history) > self.max_history:
            self.request_history = self.request_history[-self.max_history:]

    # FASE 2.3: Grounding Automático Inteligente
    def needs_grounding(self, payload: dict) -> bool:
        """
        Detecta si el payload requiere grounding con Google Search.
        
        IMPORTANTE: Gemini NO permite combinar google_search con Function Calling.
        Solo retornamos True si NO hay herramientas personalizadas en el payload.
        """
        # Verificar si hay function calling tools en el payload
        tools = payload.get("tools", [])
        has_function_calling = any(
            "function_declarations" in str(tool) or "functionCall" in str(tool)
            for tool in tools
        )
        
        # Si se solicita una salida estructurada JSON, no se permite el uso de herramientas (incluyendo Google Search)
        gen_config = payload.get("generationConfig", payload.get("generation_config", {}))
        if gen_config.get("responseMimeType") == "application/json" or gen_config.get("response_mime_type") == "application/json":
            return False

        # Si hay function calling, NO podemos usar grounding
        if has_function_calling:
            return False
        
        # Solo buscar keywords si no hay function calling
        contents = payload.get("contents", [])
        text_content = " ".join([
            str(part.get("text", ""))
            for content in contents
            for part in content.get("parts", [])
        ]).lower()
        
        return any(kw in text_content for kw in self.grounding_keywords)

    async def upload_file_to_gemini(self, file_path: str, mime_type: str) -> dict:
        """
        Sube un archivo temporal a la Gemini File API con estrategia de rotación de claves.
        """
        import os
        import json
        client = await self._get_http_client()
        last_error = None
        
        available_indices = []
        for i in range(len(self.api_keys)):
            if i not in self.invalid_keys:
                available_indices.append(i)
        random.shuffle(available_indices)
        
        display_name = os.path.basename(file_path)
        
        for idx in available_indices:
            api_key = self.api_keys[idx]
            url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
            
            metadata = {"file": {"displayName": display_name}}
            
            files = {
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file": (display_name, open(file_path, "rb"), mime_type)
            }
            
            try:
                logger.info(f"Subiendo archivo {display_name} a Gemini File API (Key index {idx})...")
                response = await client.post(url, files=files, timeout=90.0)
                
                if response.status_code == 200:
                    response_data = response.json()
                    logger.info(f"Archivo subido exitosamente a Gemini: {response_data['file']['name']}")
                    return {
                        "file_name": response_data["file"]["name"],
                        "file_uri": response_data["file"]["uri"],
                        "api_key": api_key
                    }
                
                error_data = response.json() if response.text else {}
                logger.error(f"Error subiendo archivo a Gemini (Key {idx}): {response.status_code} - {error_data}")
                last_error = Exception(f"Upload error {response.status_code}: {error_data}")
                
            except Exception as e:
                logger.error(f"Fallo al subir archivo a Gemini (Key {idx}): {e}")
                last_error = e
                
        raise last_error or Exception("No se pudo subir el archivo a la API de Gemini.")

    async def delete_file_from_gemini(self, file_name: str, api_key: str) -> bool:
        """
        Borra un archivo de la Gemini File API de forma definitiva.
        """
        client = await self._get_http_client()
        url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
        
        try:
            logger.info(f"Borrando archivo {file_name} de Gemini File API...")
            response = await client.delete(url, timeout=20.0)
            if response.status_code == 200:
                logger.info(f"Archivo {file_name} borrado exitosamente de la File API.")
                return True
            else:
                logger.warning(f"No se pudo borrar el archivo {file_name}: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Error borrando archivo {file_name} de Gemini: {e}")
            return False

    async def _create_context_cache(self, model_name: str, api_key: str, content_to_cache: dict, ttl_seconds: int = 300) -> Optional[str]:
        """Crea un recurso de Context Caching explícito en la API de Gemini (v1beta)."""
        import json
        client = await self._get_http_client()
        url = f"https://generativelanguage.googleapis.com/v1beta/cachedContents?key={api_key}"
        
        # En la API de Gemini, cachedContents requiere el formato con models/ prefijo
        model_path = model_name
        if not model_name.startswith("models/"):
            model_path = f"models/{model_name}"
            
        payload = {
            "model": model_path,
            "displayName": f"stardoc_cache_{int(time.time())}",
            "ttl": f"{ttl_seconds}s",
            "contents": [content_to_cache]
        }
        
        try:
            logger.info(f"💾 Creando Context Cache en Gemini para el modelo {model_name}...")
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            if response.status_code in (200, 201):
                data = response.json()
                cache_id = data.get("name")
                logger.info(f"✅ Context Cache creada con éxito en Gemini: {cache_id}")
                return cache_id
            else:
                logger.warning(f"⚠️ No se pudo crear Context Cache. Status: {response.status_code}, Body: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error creando Context Cache: {e}", exc_info=True)
            return None

    async def _apply_context_caching(self, payload: dict, model_name: str, api_key: str) -> None:
        """
        Evalúa el primer mensaje de contents (instrucciones + RAG).
        Si supera los 32,768 tokens, crea una caché en la API de Gemini (o la reutiliza)
        y muta el payload para incluir cachedContent.
        """
        import hashlib
        import json
        
        contents = payload.get("contents", [])
        if not contents or len(contents) <= 1:
            return
            
        first_content = contents[0]
        # Solo cachamos si el primer elemento contiene parts
        first_text = ""
        if "parts" in first_content:
            first_text = " ".join([p.get("text", "") for p in first_content["parts"] if "text" in p])
            
        if not first_text:
            return
            
        estimated_tokens = self._estimate_tokens(first_text)
        # El límite mínimo oficial de Gemini para Context Caching es 32768 tokens
        if estimated_tokens < 32768:
            return
            
        # Generar hash único del contenido para indexación
        cache_key = hashlib.sha256(first_text.encode("utf-8")).hexdigest()
        
        # Verificar si ya existe en memoria y no ha expirado (TTL de 300 segundos)
        now = time.time()
        cached_info = self.context_caches.get(cache_key)
        
        cache_id = None
        if cached_info and (now - cached_info["created_at"] < 280): # Margen de seguridad de 20s
            cache_id = cached_info["cache_id"]
            logger.info(f"⚡ Reutilizando Context Cache existente para hash {cache_key[:10]}: {cache_id}")
        else:
            # Crear la caché en la API de Gemini
            cache_id = await self._create_context_cache(model_name, api_key, first_content, ttl_seconds=300)
            if cache_id:
                self.context_caches[cache_key] = {
                    "cache_id": cache_id,
                    "created_at": now,
                    "model": model_name
                }
                
        if cache_id:
            # Mutar el payload de Gemini
            payload["cachedContent"] = cache_id
            # El primer elemento que se guardó en la caché se remueve del arreglo "contents"
            # enviado en la llamada subsiguiente a generateContent
            payload["contents"] = contents[1:]
            logger.info(f"⚡ Context Caching aplicado con éxito. Payload contents reducidos de {len(contents)} a {len(payload['contents'])}.")

    async def generate_content(
        self,
        payload: dict,
        model: Optional[str] = None,
        timeout: float = 45.0,
        add_grounding: bool = False,
        api_key: Optional[str] = None
    ) -> dict:
        """
        Genera contenido con estrategia de 'Cascada de Modelos' usando httpx directo.
        
        Mejoras aplicadas:
        - FASE 1.1: Context Caching (payload estructurado para maximizar cache hits)
        - FASE 1.3: Métricas de latencia y costos
        - FASE 2.1: Soporte para code execution (tool en payload)
        - FASE 2.3: Grounding automático si detecta keywords legales
        - FASE 3.1: Circuit Breaker para modelos degradados

        Args:
            payload: El payload JSON para la API de Gemini
            model: Modelo específico a usar (si None, usa cascada)
            timeout: Timeout en segundos para la request
            add_grounding: Si True, agrega google_search tool automáticamente

        Returns:
            dict: La respuesta parseada de la API de Gemini
        """
        last_error = None
        client = await self._get_http_client()

        # FASE 2.3: Auto-detectar si necesita grounding
        if add_grounding or self.needs_grounding(payload):
            tools = payload.get("tools", [])
            if not any("google_search" in str(t) for t in tools):
                tools.append({"google_search": {}})
                payload["tools"] = tools
                logger.info("🔍 Grounding con Google Search activado automáticamente")

        # FASE 1.1: Estructurar payload para maximizar context caching
        # Gemini implicit caching reutiliza prefijos compartidos
        # El system instruction debe ser siempre el primer content

        models_to_try = [model] if model else self.models.copy()
        
        # Deduplicar herramientas para evitar declaraciones repetidas en la API de Gemini
        self._deduplicate_tools(payload)

        # Estimar tokens de entrada para métricas
        input_text = str(payload)
        estimated_input_tokens = self._estimate_tokens(input_text)

        # Cascada de Modelos
        for model_name in models_to_try:
            # FASE 3.1 & Redis: Verificar Circuit Breaker
            try:
                from app.services.redis_circuit_breaker import RedisCircuitBreaker
                if not await RedisCircuitBreaker.can_execute(model_name):
                    logger.warning(f"⛔ Redis Circuit Breaker OPEN para {model_name}, saltando")
                    continue
            except Exception as ex:
                # Degradación local en memoria
                cb = self.circuit_breakers.get(model_name)
                if cb and not cb.can_execute():
                    logger.warning(f"⛔ Local Circuit Breaker OPEN para {model_name}, saltando")
                    continue

            # Rotación de Claves para cada modelo (asíncrono)
            available_indices = []
            if api_key:
                try:
                    idx = self.api_keys.index(api_key)
                    available_indices = [idx]
                except ValueError:
                    logger.warning(f"La clave API especificada no se encuentra en el pool, usando rotación.")
                    for i in range(len(self.api_keys)):
                        if await self._get_key_status(i, model_name):
                            available_indices.append(i)
                    random.shuffle(available_indices)
            else:
                for i in range(len(self.api_keys)):
                    if await self._get_key_status(i, model_name):
                        available_indices.append(i)
                random.shuffle(available_indices)

            for idx in available_indices:
                api_key = self.api_keys[idx]
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

                import copy
                request_payload = copy.deepcopy(payload)
                await self._apply_context_caching(request_payload, model_name, api_key)

                self.model_stats[model_name]["total"] += 1
                start_time = time.time()

                try:
                    logger.info(f"🔄 Intentando con {model_name} (Clave {idx})")

                    response = await client.post(
                        url,
                        json=request_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=timeout
                    )

                    latency_ms = (time.time() - start_time) * 1000

                    # Manejo de respuestas
                    if response.status_code == 200:
                        response_data = response.json()
                        output_text = str(response_data)
                        estimated_output_tokens = self._estimate_tokens(output_text)
                        
                        # FASE 3.1 & Redis: Record success en Circuit Breaker
                        try:
                            from app.services.redis_circuit_breaker import RedisCircuitBreaker
                            await RedisCircuitBreaker.record_success(model_name)
                        except Exception:
                            pass
                        cb = self.circuit_breakers.get(model_name)
                        if cb:
                            cb.record_success()
                        
                        # FASE 1.3: Record métricas
                        self.model_stats[model_name]["success"] += 1
                        self._record_request(
                            model_name, latency_ms,
                            estimated_input_tokens, estimated_output_tokens,
                            success=True
                        )
                        
                        logger.info(f"✅ {model_name} respondió en {latency_ms:.0f}ms")
                        return response_data

                    # Errores - decidir si hacer fallback o reintentar
                    error_data = response.json() if response.text else {}
                    error_str = f"{response.status_code}: {error_data}"

                    if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_str:
                        logger.warning(f"⏳ Cuota agotada para {model_name} con clave {idx}. Marcando en cooldown.")
                        self.exhausted_keys[f"{idx}:{model_name}"] = time.time()
                        try:
                            from app.services.redis_circuit_breaker import RedisCircuitBreaker
                            await RedisCircuitBreaker.mark_key_exhausted(idx, model_name, cooldown=60)
                            await RedisCircuitBreaker.record_failure(model_name)
                        except Exception:
                            pass
                        self.model_stats[model_name]["failure"] += 1
                        cb = self.circuit_breakers.get(model_name)
                        if cb:
                            cb.record_failure()
                        self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                        last_error = Exception(f"429 Rate Limit: {error_str}")
                        continue  # Intentar siguiente clave/modelo

                    elif response.status_code in (500, 503, 504):
                        logger.warning(f"⚠️ Error {response.status_code} ({model_name}). Reintentando tras breve pausa o usando fallback.")
                        self.model_stats[model_name]["failure"] += 1
                        try:
                            from app.services.redis_circuit_breaker import RedisCircuitBreaker
                            await RedisCircuitBreaker.record_failure(model_name)
                        except Exception:
                            pass
                        cb = self.circuit_breakers.get(model_name)
                        if cb: cb.record_failure()
                        self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                        last_error = Exception(f"Server Error {response.status_code}: {error_str}")
                        # Demora exponencial/estratégica moderada antes de rotar para aliviar demanda
                        await asyncio.sleep(1.5)
                        break  # Romper loop de claves, ir al siguiente modelo (ej: 1.5-flash)

                    elif response.status_code == 400:
                        # Verificar si es por clave API inválida
                        error_msg = error_data.get("error", {}).get("message", "")
                        error_reason = ""
                        details = error_data.get("error", {}).get("details", [])
                        for detail in details:
                            if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
                                error_reason = detail.get("reason", "")
                        
                        if "API key not valid" in error_msg or error_reason == "API_KEY_INVALID":
                            logger.error(f"❌ La clave de API en el índice {idx} es inválida (API_KEY_INVALID). Removiéndola de la rotación.")
                            self.invalid_keys.add(idx)
                            continue  # Intentar la siguiente clave para este modelo
                        
                        logger.error(f"❌ Error de request (400) para {model_name}: {error_str}")
                        self.model_stats[model_name]["failure"] += 1
                        self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                        raise Exception(f"Bad Request (400): {error_str}")

                    else:
                        logger.error(f"❌ Error inesperado ({response.status_code}) para {model_name}: {error_str}")
                        self.model_stats[model_name]["failure"] += 1
                        self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                        last_error = Exception(f"Error {response.status_code}: {error_str}")
                        continue

                except httpx.TimeoutException:
                    latency_ms = (time.time() - start_time) * 1000
                    logger.warning(f"⏰ Timeout para {model_name} con clave {idx} ({latency_ms:.0f}ms)")
                    self.model_stats[model_name]["failure"] += 1
                    try:
                        from app.services.redis_circuit_breaker import RedisCircuitBreaker
                        await RedisCircuitBreaker.record_failure(model_name)
                    except Exception:
                        pass
                    cb = self.circuit_breakers.get(model_name)
                    if cb:
                        cb.record_failure()
                    self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                    last_error = Exception(f"Timeout para {model_name}")
                    continue

                except httpx.ConnectError as e:
                    latency_ms = (time.time() - start_time) * 1000
                    logger.error(f"🔌 Error de conexión para {model_name}: {e}")
                    self.model_stats[model_name]["failure"] += 1
                    try:
                        from app.services.redis_circuit_breaker import RedisCircuitBreaker
                        await RedisCircuitBreaker.record_failure(model_name)
                    except Exception:
                        pass
                    cb = self.circuit_breakers.get(model_name)
                    if cb:
                        cb.record_failure()
                    self._record_request(model_name, latency_ms, estimated_input_tokens, 0, success=False)
                    last_error = e
                    break  # Ir al siguiente modelo

        # Todos los modelos fallaron
        logger.error(f"💥 Fallo total: Todos los modelos y claves agotados. Stats: {self.get_model_stats()}")

        if last_error:
            error_str = str(last_error)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                raise Exception(
                    "Cuota de Gemini API (429) excedida. Has superado los límites de uso o el plan gratuito."
                )
            raise last_error

        raise Exception("Servicio de IA no disponible. Todos los modelos fallaron.")

    async def stream_generate_content(
        self,
        payload: dict,
        model: Optional[str] = None
    ):
        """
        Generador asíncrono para streaming real (Server-Sent Events) directo de Gemini.
        Diseñado para la fase final del Agente u operaciones directas de texto.
        Maneja cascada de modelos y emite json dumps compatibles con el frontend.
        """
        last_error = None
        client = await self._get_http_client()
        models_to_try = [model] if model else self.models.copy()
        import json

        # Deduplicar herramientas para evitar declaraciones repetidas en modo streaming
        self._deduplicate_tools(payload)

        for model_name in models_to_try:
            # 1. Verificar Circuit Breaker compartido en Redis
            try:
                from app.services.redis_circuit_breaker import RedisCircuitBreaker
                if not await RedisCircuitBreaker.can_execute(model_name):
                    logger.warning(f"⛔ Redis Circuit Breaker OPEN para {model_name} en STREAM, saltando")
                    continue
            except Exception:
                cb = self.circuit_breakers.get(model_name)
                if cb and not cb.can_execute():
                    logger.warning(f"⛔ Local Circuit Breaker OPEN para {model_name} en STREAM, saltando")
                    continue

            # 2. Obtener claves de API válidas evaluando asíncronamente
            available_indices = []
            for i in range(len(self.api_keys)):
                if await self._get_key_status(i, model_name):
                    available_indices.append(i)
            
            import random
            random.shuffle(available_indices)
            
            for idx in available_indices:
                api_key = self.api_keys[idx]
                # Modificamos endpoint para stream
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={api_key}"

                import copy
                request_payload = copy.deepcopy(payload)
                await self._apply_context_caching(request_payload, model_name, api_key)

                self.model_stats[model_name]["total"] += 1
                try:
                    logger.info(f"🔄 Intentando STREAM con {model_name} (Clave {idx})")
                    async with client.stream(
                        "POST", 
                        url, 
                        json=request_payload, 
                        headers={"Content-Type": "application/json"},
                        timeout=50.0
                    ) as response:
                        
                        if response.status_code == 200:
                            self.model_stats[model_name]["success"] += 1
                            # Registrar éxito en el circuit breaker
                            try:
                                from app.services.redis_circuit_breaker import RedisCircuitBreaker
                                await RedisCircuitBreaker.record_success(model_name)
                            except Exception:
                                pass
                            cb = self.circuit_breakers.get(model_name)
                            if cb:
                                cb.record_success()

                            async for line in response.aiter_lines():
                                line = line.strip()
                                if line.startswith("data: "):
                                    chunk_data = line[6:]
                                    if chunk_data:
                                        try:
                                            # Verificamos que sea JSON válido
                                            parsed = json.loads(chunk_data)
                                            # Extraemos la primer parte de la API para que el FastAPI no tenga que parsearlo complejo
                                            candidate = parsed.get("candidates", [{}])[0]
                                            parts = candidate.get("content", {}).get("parts", [])
                                            
                                            text_chunk = ""
                                            for p in parts:
                                                if "text" in p:
                                                    text_chunk += p["text"]
                                            
                                            if text_chunk:
                                                yield {"type": "chunk", "text": text_chunk}
                                        except Exception as parse_e:
                                            logger.warning(f"Error parseando SSE chunk: {parse_e}")
                            return  # Si iteró todo OK, terminamos

                        # Si no es 200, registramos fallo
                        error_text = await response.aread()
                        error_str = error_text.decode('utf-8')
                        logger.warning(f"Error HTTP {response.status_code} en stream: {error_str}")

                        # Verificar si el fallo es por clave API inválida
                        is_api_key_invalid = False
                        try:
                            error_data = json.loads(error_str)
                            error_msg = error_data.get("error", {}).get("message", "")
                            error_reason = ""
                            details = error_data.get("error", {}).get("details", [])
                            for detail in details:
                                if detail.get("@type") == "type.googleapis.com/google.rpc.ErrorInfo":
                                    error_reason = detail.get("reason", "")
                            if "API key not valid" in error_msg or error_reason == "API_KEY_INVALID":
                                is_api_key_invalid = True
                        except Exception:
                            if "API key not valid" in error_str or "API_KEY_INVALID" in error_str:
                                is_api_key_invalid = True

                        if is_api_key_invalid:
                            logger.error(f"❌ La clave de API en el índice {idx} es inválida (Error {response.status_code} en stream). Removiéndola de la rotación.")
                            self.invalid_keys.add(idx)
                            continue  # Intentar la siguiente clave para este modelo sin afectar al circuit breaker del modelo

                        self.model_stats[model_name]["failure"] += 1
                        
                        # Registrar fallo en el circuit breaker
                        try:
                            from app.services.redis_circuit_breaker import RedisCircuitBreaker
                            await RedisCircuitBreaker.record_failure(model_name)
                        except Exception:
                            pass
                        cb = self.circuit_breakers.get(model_name)
                        if cb:
                            cb.record_failure()

                        if response.status_code == 429 or "RESOURCE_EXHAUSTED" in error_str:
                            self.exhausted_keys[f"{idx}:{model_name}"] = time.time()
                            try:
                                from app.services.redis_circuit_breaker import RedisCircuitBreaker
                                await RedisCircuitBreaker.mark_key_exhausted(idx, model_name, cooldown=60)
                            except Exception:
                                pass
                        elif response.status_code in (500, 503, 504):
                            # Error servidor, espera táctica mayor antes de fallback
                            await asyncio.sleep(1.5)
                            break # Fallback on next model
                
                except httpx.TimeoutException:
                     logger.warning(f"⏰ Timeout en STREAM para {model_name} con clave {idx}")
                     self.model_stats[model_name]["failure"] += 1
                     try:
                         from app.services.redis_circuit_breaker import RedisCircuitBreaker
                         await RedisCircuitBreaker.record_failure(model_name)
                     except Exception:
                         pass
                     cb = self.circuit_breakers.get(model_name)
                     if cb:
                         cb.record_failure()
                except httpx.ConnectError as e:
                     logger.error(f"🔌 Error de conexión STREAM para {model_name}: {e}")
                     self.model_stats[model_name]["failure"] += 1
                     try:
                         from app.services.redis_circuit_breaker import RedisCircuitBreaker
                         await RedisCircuitBreaker.record_failure(model_name)
                     except Exception:
                         pass
                     cb = self.circuit_breakers.get(model_name)
                     if cb:
                         cb.record_failure()
                     break

        # Si llegamos aquí, los modelos fallaron. Yield simple de error.
        yield {"type": "error", "error": "No se pudo establecer el stream con ningún modelo."}

    # FASE 1.3: Métricas Avanzadas y Dashboard
    def get_model_stats(self) -> Dict[str, Dict[str, Any]]:

        """Retorna métricas detalladas por modelo."""
        stats = {}
        for model_name, data in self.model_stats.items():
            total = data["total"]
            success = data["success"]
            failure = data["failure"]
            avg_latency = data["total_latency_ms"] / total if total > 0 else 0
            success_rate = (success / total * 100) if total > 0 else 0
            
            # FASE 1.3: Circuit Breaker state
            cb_state = self.circuit_breakers[model_name].state.value if model_name in self.circuit_breakers else "unknown"
            
            stats[model_name] = {
                **data,
                "avg_latency_ms": round(avg_latency, 2),
                "success_rate_percent": round(success_rate, 2),
                "circuit_breaker_state": cb_state,
                "health_status": self.model_health.get(model_name, "unknown"),
            }
        return stats

    def get_detailed_metrics(self) -> Dict[str, Any]:
        """Retorna métricas globales detalladas para dashboard."""
        total_requests = sum(s["total"] for s in self.model_stats.values())
        total_success = sum(s["success"] for s in self.model_stats.values())
        total_failures = sum(s["failure"] for s in self.model_stats.values())
        total_latency = sum(s["total_latency_ms"] for s in self.model_stats.values())
        total_tokens = sum(s["total_tokens_estimated"] for s in self.model_stats.values())
        
        # Estimación de costos (precios aproximados Gemini 2.5 Flash)
        # Input: $0.10/1M tokens, Output: $0.40/1M tokens
        estimated_cost_usd = (total_tokens * 0.25) / 1_000_000
        
        # Requests en último minuto
        now = time.time()
        recent_requests = [r for r in self.request_history if now - r["timestamp"] < 60]
        recent_failures = [r for r in recent_requests if not r["success"]]
        
        return {
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failures": total_failures,
            "global_success_rate": round((total_success / total_requests * 100) if total_requests > 0 else 0, 2),
            "avg_latency_ms": round((total_latency / total_requests) if total_requests > 0 else 0, 2),
            "total_tokens_estimated": total_tokens,
            "estimated_cost_usd": round(estimated_cost_usd, 6),
            "active_api_keys": len(self.api_keys),
            "requests_last_minute": len(recent_requests),
            "failures_last_minute": len(recent_failures),
            "models": self.get_model_stats(),
            "circuit_breakers": {
                model: cb.state.value
                for model, cb in self.circuit_breakers.items()
            },
            "health_status": self.model_health,
        }

    # FASE 3.3: Health Checker Proactivo
    async def start_health_checker(self, interval_seconds: int = 300):
        """Inicia health checker en background cada N segundos (default: 5 min)."""
        if self._health_checker_started:
            return
        
        self._health_checker_started = True
        self._health_checker_task = asyncio.create_task(
            self._health_checker_loop(interval_seconds)
        )
        logger.info(f"🏥 Health Checker iniciado (intervalo: {interval_seconds}s)")

    async def _health_checker_loop(self, interval_seconds: int):
        """Loop principal del health checker."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._run_health_checks()
            except asyncio.CancelledError:
                logger.info("🏥 Health Checker cancelado")
                break
            except Exception as e:
                logger.error(f"🏥 Error en health checker: {e}")

    async def _run_health_checks(self):
        """Ejecuta health checks para todos los modelos."""
        logger.info("🏥 Ejecutando health checks...")
        
        for model in self.models:
            try:
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                    "generationConfig": {"maxOutputTokens": 5, "temperature": 0}
                }
                await self.generate_content(payload=payload, model=model, timeout=10.0)
                self.model_health[model] = "healthy"
                logger.info(f"✅ Health check OK para {model}")
            except Exception as e:
                self.model_health[model] = f"unhealthy: {str(e)[:100]}"
                logger.warning(f"❌ Health check falló para {model}: {e}")

    async def run_health_check_now(self) -> Dict[str, str]:
        """Ejecuta health check inmediato (útil para endpoint manual)."""
        await self._run_health_checks()
        return self.model_health.copy()


# Instancia global
ai_service = AIService()
