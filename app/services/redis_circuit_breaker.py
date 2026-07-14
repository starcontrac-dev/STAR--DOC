"""
Circuit Breaker distribuido respaldado por Redis.
Permite que múltiples workers compartan el estado de disponibilidad de modelos y API keys.
"""
import logging
from typing import Optional
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

class RedisCircuitBreaker:
    PREFIX = "cb"
    
    @staticmethod
    async def record_failure(model: str, threshold: int = 5) -> str:
        """Registra un fallo para el modelo. Si supera el umbral, abre el circuito."""
        try:
            pool = await redis_manager.get_pool(db=3)
            key = f"{RedisCircuitBreaker.PREFIX}:{model}:failures"
            failures = await pool.incr(key)
            await pool.expire(key, 300)  # Reset automático de fallos en 5 min
            
            if failures >= threshold:
                await pool.setex(f"{RedisCircuitBreaker.PREFIX}:{model}:state", 120, "open")
                logger.warning(f"🚨 Circuit Breaker ABIERTO para el modelo '{model}'. Bloqueado por 120s.")
                return "open"
            return "closed"
        except Exception as e:
            logger.warning(f"Error al registrar fallo en Redis Circuit Breaker: {e}")
            return "closed"
    
    @staticmethod
    async def record_success(model: str):
        """Registra un éxito. Resetea el contador de fallos y cierra el circuito."""
        try:
            pool = await redis_manager.get_pool(db=3)
            pipe = pool.pipeline()
            pipe.delete(f"{RedisCircuitBreaker.PREFIX}:{model}:failures")
            pipe.delete(f"{RedisCircuitBreaker.PREFIX}:{model}:state")
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Error al registrar éxito en Redis Circuit Breaker: {e}")
    
    @staticmethod
    async def can_execute(model: str) -> bool:
        """Verifica si el modelo está disponible (el circuito no está ABIERTO)."""
        try:
            pool = await redis_manager.get_pool(db=3)
            state = await pool.get(f"{RedisCircuitBreaker.PREFIX}:{model}:state")
            return state != "open"
        except Exception as e:
            logger.warning(f"Error al validar estado en Redis Circuit Breaker (degradación activa): {e}")
            return True  # Fallback a permitir ejecución si Redis falla
    
    @staticmethod
    async def mark_key_exhausted(key_index: int, model: str, cooldown: int = 60):
        """Marca una API key específica como agotada (recibió 429) por un tiempo de cooldown."""
        try:
            pool = await redis_manager.get_pool(db=3)
            # Clave: apikey_cooldown:{key_index}:{model}
            await pool.setex(f"apikey_cooldown:{key_index}:{model}", cooldown, "exhausted")
            logger.info(f"⏳ Clave de API en índice {key_index} marcada en cooldown para '{model}' por {cooldown}s.")
        except Exception as e:
            logger.warning(f"Error al marcar clave agotada en Redis: {e}")
    
    @staticmethod
    async def is_key_available(key_index: int, model: str) -> bool:
        """Verifica si una clave de API está disponible para uso (no está en cooldown)."""
        try:
            pool = await redis_manager.get_pool(db=3)
            return not await pool.exists(f"apikey_cooldown:{key_index}:{model}")
        except Exception as e:
            logger.warning(f"Error al verificar disponibilidad de clave en Redis (degradación activa): {e}")
            return True  # Fallback: asumir que está disponible
