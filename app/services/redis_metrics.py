"""
MetricsCollector respaldado por Redis.
Usa estructuras nativas de Redis para contadores atómicos y ranking.
"""
import logging
import time
import json
from typing import List, Dict, Any, Optional
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

class RedisMetrics:
    """Extiende MetricsCollector con persistencia en Redis DB 3."""
    
    PREFIX = "metrics"
    
    @staticmethod
    async def record_tool_call(tool_name: str, duration_ms: float, success: bool):
        """Registra una ejecución de herramienta con contadores atómicos."""
        try:
            pool = await redis_manager.get_pool(db=3)
            pipe = pool.pipeline()
            
            # Contadores atómicos (HINCRBY es O(1) y thread-safe)
            pipe.hincrby(f"{RedisMetrics.PREFIX}:tool:{tool_name}", "calls", 1)
            pipe.hincrby(f"{RedisMetrics.PREFIX}:tool:{tool_name}", 
                         "success" if success else "failure", 1)
            pipe.hincrbyfloat(f"{RedisMetrics.PREFIX}:tool:{tool_name}", 
                              "total_ms", duration_ms)
            
            # Sorted Set para ranking global (score = total calls)
            pipe.zincrby(f"{RedisMetrics.PREFIX}:tools:ranking", 1, tool_name)
            
            # Historial reciente (lista con LPUSH + LTRIM)
            entry = json.dumps({
                "tool": tool_name,
                "duration_ms": round(duration_ms, 2),
                "success": success,
                "timestamp": time.time()
            })
            pipe.lpush(f"{RedisMetrics.PREFIX}:tool_history", entry)
            pipe.ltrim(f"{RedisMetrics.PREFIX}:tool_history", 0, 499)  # Últimos 500
            
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Error registrando métricas de herramienta en Redis: {e}")
    
    @staticmethod
    async def record_ai_request(model: str, latency_ms: float, success: bool, tokens: int = 0):
        """Registra una petición al servicio de IA."""
        try:
            pool = await redis_manager.get_pool(db=3)
            pipe = pool.pipeline()
            
            pipe.hincrby(f"{RedisMetrics.PREFIX}:ai:{model}", "total", 1)
            pipe.hincrby(f"{RedisMetrics.PREFIX}:ai:{model}", 
                         "success" if success else "failure", 1)
            pipe.hincrbyfloat(f"{RedisMetrics.PREFIX}:ai:{model}", 
                              "total_latency_ms", latency_ms)
            pipe.hincrby(f"{RedisMetrics.PREFIX}:ai:{model}", "total_tokens", tokens)
            
            # Historial para percentiles (últimos 1000)
            pipe.lpush(f"{RedisMetrics.PREFIX}:ai_history", 
                       json.dumps({"model": model, "latency_ms": latency_ms, 
                                  "success": success, "ts": time.time()}))
            pipe.ltrim(f"{RedisMetrics.PREFIX}:ai_history", 0, 999)
            
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Error registrando métricas de IA en Redis: {e}")
    
    @staticmethod
    async def get_tools_ranking(top: int = 15) -> list:
        """Obtiene las herramientas más usadas (Sorted Set descendente)."""
        try:
            pool = await redis_manager.get_pool(db=3)
            ranking = await pool.zrevrange(
                f"{RedisMetrics.PREFIX}:tools:ranking", 0, top - 1, withscores=True
            )
            return [{"name": name, "calls": int(score)} for name, score in ranking]
        except Exception as e:
            logger.warning(f"Error obteniendo ranking de herramientas de Redis: {e}")
            return []
    
    @staticmethod
    async def get_global_counters() -> dict:
        """Obtiene contadores globales del sistema."""
        try:
            pool = await redis_manager.get_pool(db=3)
            return {
                "total_docs": int(await pool.get(f"{RedisMetrics.PREFIX}:docs:total") or 0),
                "total_conversations": int(await pool.get(f"{RedisMetrics.PREFIX}:conversations") or 0),
                "total_messages": int(await pool.get(f"{RedisMetrics.PREFIX}:messages") or 0),
            }
        except Exception as e:
            logger.warning(f"Error obteniendo contadores globales de Redis: {e}")
            return {"total_docs": 0, "total_conversations": 0, "total_messages": 0}
    
    @staticmethod
    async def increment_counter(counter_name: str, amount: int = 1):
        """Incrementa un contador global en Redis DB 3."""
        try:
            pool = await redis_manager.get_pool(db=3)
            await pool.incrby(f"{RedisMetrics.PREFIX}:{counter_name}", amount)
        except Exception as e:
            logger.warning(f"Error incrementando contador '{counter_name}' en Redis: {e}")
            
    @staticmethod
    async def get_tool_metrics(tool_name: str) -> dict:
        """Retorna las métricas acumuladas de una herramienta específica."""
        try:
            pool = await redis_manager.get_pool(db=3)
            data = await pool.hgetall(f"{RedisMetrics.PREFIX}:tool:{tool_name}")
            if not data:
                return {"calls": 0, "success": 0, "failure": 0, "total_ms": 0.0}
            return {
                "calls": int(data.get("calls", 0)),
                "success": int(data.get("success", 0)),
                "failure": int(data.get("failure", 0)),
                "total_ms": float(data.get("total_ms", 0.0))
            }
        except Exception as e:
            logger.warning(f"Error obteniendo métricas de herramienta '{tool_name}' de Redis: {e}")
            return {"calls": 0, "success": 0, "failure": 0, "total_ms": 0.0}

    @staticmethod
    async def get_ai_metrics(model: str) -> dict:
        """Retorna las métricas acumuladas de solicitudes de IA para un modelo."""
        try:
            pool = await redis_manager.get_pool(db=3)
            data = await pool.hgetall(f"{RedisMetrics.PREFIX}:ai:{model}")
            if not data:
                return {"total": 0, "success": 0, "failure": 0, "total_latency_ms": 0.0, "total_tokens": 0}
            return {
                "total": int(data.get("total", 0)),
                "success": int(data.get("success", 0)),
                "failure": int(data.get("failure", 0)),
                "total_latency_ms": float(data.get("total_latency_ms", 0.0)),
                "total_tokens": int(data.get("total_tokens", 0))
            }
        except Exception as e:
            logger.warning(f"Error obteniendo métricas de IA para '{model}' de Redis: {e}")
            return {"total": 0, "success": 0, "failure": 0, "total_latency_ms": 0.0, "total_tokens": 0}
