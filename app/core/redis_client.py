"""
Cliente Redis asíncrono centralizado para STAR-DOC.

Patrón Singleton con connection pool optimizado para producción.
Utiliza redis.asyncio (redis-py v5+) con hiredis como parser C nativo si está disponible.
"""
import logging
import redis.asyncio as redis
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisManager:
    """
    Gestor centralizado de conexiones Redis.
    
    Provee pools dedicados por base de datos lógica:
    - DB 0: Sesiones JWT y tokens de revocación
    - DB 1: Rate Limiting distribuido (SlowAPI backend)
    - DB 2: Caché de datos (templates, dashboard, métricas)
    - DB 3: Métricas en tiempo real (contadores, histogramas) e IA Circuit Breaker
    - DB 4: Pub/Sub y eventos en tiempo real
    - DB 5: Nonces Web3 y estados OAuth efímeros
    """
    _instance: Optional['RedisManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._pools: dict[int, redis.Redis] = {}
        self._initialized = True
    
    async def get_pool(self, db: int = 0) -> redis.Redis:
        """Obtiene o crea un pool de conexión para la DB especificada."""
        if db not in self._pools:
            self._pools[db] = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=db,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
            )
        return self._pools[db]
    
    async def health_check(self) -> dict:
        """Verifica la conectividad con Redis."""
        try:
            pool = await self.get_pool(0)
            # Realizar un PING directo para validar la conexión real
            pong = await pool.ping()
            if not pong:
                raise ConnectionError("Redis no respondió al PING")
                
            info = await pool.info(section="server")
            return {
                "status": "healthy",
                "version": info.get("redis_version"),
                "uptime_seconds": info.get("uptime_in_seconds"),
                "connected_clients": info.get("connected_clients"),
            }
        except Exception as e:
            logger.error(f"Redis health check falló: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    async def close_all(self):
        """Cierra todos los pools de conexión."""
        for db, pool in self._pools.items():
            try:
                await pool.aclose()
                logger.info(f"Pool Redis DB {db} cerrado correctamente.")
            except Exception as e:
                logger.warning(f"Error cerrando pool Redis DB {db}: {e}")
        self._pools.clear()


# Instancia Singleton global
redis_manager = RedisManager()


# --- Dependency para FastAPI ---
async def get_redis(db: int = 0) -> redis.Redis:
    """Dependency de FastAPI para inyectar cliente Redis."""
    return await redis_manager.get_pool(db)
