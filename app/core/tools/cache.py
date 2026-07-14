import hashlib
import time
from typing import Optional, Tuple, Any

class MemoryCache:
    """
    Caché simple en memoria para evitar llamadas redundantes a APIs externas (Brave, etc)
    y para persistir resultados computables a nivel de proceso durante el tiempo de vida
    o hasta el TTL definido.
    """
    def __init__(self, ttl_seconds: int = 86400):
        # 86400s = 24h
        self.cache = {}
        self.ttl = ttl_seconds

    def _generate_key(self, namespace: str, query_data: str) -> str:
        raw = f"{namespace}:{query_data}"
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def get(self, namespace: str, query_data: str) -> Optional[Any]:
        key = self._generate_key(namespace, query_data)
        if key in self.cache:
            result, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return result
            # Si expiró, se limpia
            del self.cache[key]
        return None

    def set(self, namespace: str, query_data: str, result: Any) -> None:
        key = self._generate_key(namespace, query_data)
        self.cache[key] = (result, time.time())

    def clear(self):
        self.cache.clear()

global_cache = MemoryCache()
