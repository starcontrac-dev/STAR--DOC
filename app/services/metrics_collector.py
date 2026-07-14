"""
MetricsCollector — Colector de métricas en tiempo real para STAR-DOC.

Singleton que acumula estadísticas de uso del sistema:
- Ejecuciones de herramientas (tools) por nombre
- Activaciones de skills
- Tiempos de respuesta
- Conteos de documentos generados por tipo

Diseñado para datos en memoria (volátiles al reiniciar),
complementando las métricas persistentes del AIService.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Singleton para recopilar métricas operativas del sistema STAR-DOC.
    
    Los datos se mantienen en memoria y se resetean al reiniciar.
    Para datos persistentes, usar la base de datos (Fase futura).
    """
    _instance: Optional['MetricsCollector'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsCollector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Timestamp de arranque del servidor
        self.server_start_time: float = time.time()

        # --- Métricas de Tools ---
        # Estructura: {nombre_herramienta: {calls: int, success: int, failure: int, total_ms: float}}
        self.tool_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "success": 0, "failure": 0, "total_ms": 0.0}
        )

        # Historial de ejecuciones recientes (últimos 500)
        self.tool_history: List[Dict[str, Any]] = []
        self.max_tool_history: int = 500

        # --- Métricas de Skills ---
        # Estructura: {skill_id: {activations: int, last_used: timestamp}}
        self.skill_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"activations": 0, "last_used": None}
        )

        # --- Métricas de Documentos ---
        self.docs_generated: int = 0
        self.docs_by_type: Dict[str, int] = defaultdict(int)

        # --- Métricas de Conversaciones ---
        self.conversations_count: int = 0
        self.messages_count: int = 0

        self._initialized = True
        logger.info("📊 MetricsCollector inicializado")

    # --- REGISTROS DE EVENTOS ---

    def record_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        skill_id: Optional[str] = None,
        params_summary: Optional[str] = None
    ):
        """Registra la ejecución de una herramienta (tool)."""
        stats = self.tool_stats[tool_name]
        stats["calls"] += 1
        stats["total_ms"] += duration_ms
        if success:
            stats["success"] += 1
        else:
            stats["failure"] += 1

        # Historial reciente
        entry = {
            "tool": tool_name,
            "skill": skill_id or "global",
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "timestamp": time.time(),
            "params": params_summary or ""
        }
        self.tool_history.append(entry)

        # Trim historial
        if len(self.tool_history) > self.max_tool_history:
            self.tool_history = self.tool_history[-self.max_tool_history:]

        # Si hay skill, registrarlo
        if skill_id:
            self.skill_stats[skill_id]["activations"] += 1
            self.skill_stats[skill_id]["last_used"] = time.time()

        # Dual-write a Redis de forma asíncrona no bloqueante
        try:
            import asyncio
            from app.services.redis_metrics import RedisMetrics
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(RedisMetrics.record_tool_call(tool_name, duration_ms, success))
                if skill_id:
                    # Guardar activaciones de skill en Redis DB 3
                    loop.create_task(RedisMetrics.increment_counter(f"skill:{skill_id}:activations", 1))
        except RuntimeError:
            pass
        except Exception as e:
            logger.warning(f"Fallo al despachar métrica de tool a Redis: {e}")

    def record_document_generated(self, doc_type: str = "general"):
        """Registra la generación de un documento."""
        self.docs_generated += 1
        self.docs_by_type[doc_type] += 1

        # Dual-write a Redis
        try:
            import asyncio
            from app.services.redis_metrics import RedisMetrics
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(RedisMetrics.increment_counter("docs:total", 1))
                loop.create_task(RedisMetrics.increment_counter(f"docs:type:{doc_type}", 1))
        except RuntimeError:
            pass

    def record_conversation(self):
        """Registra una nueva conversación iniciada."""
        self.conversations_count += 1

        # Dual-write a Redis
        try:
            import asyncio
            from app.services.redis_metrics import RedisMetrics
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(RedisMetrics.increment_counter("conversations", 1))
        except RuntimeError:
            pass

    def record_message(self):
        """Registra un mensaje procesado."""
        self.messages_count += 1

        # Dual-write a Redis
        try:
            import asyncio
            from app.services.redis_metrics import RedisMetrics
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(RedisMetrics.increment_counter("messages", 1))
        except RuntimeError:
            pass

    # --- CONSULTAS DE MÉTRICAS ---

    def get_uptime(self) -> str:
        """Retorna el uptime del servidor en formato legible."""
        elapsed = time.time() - self.server_start_time
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m {seconds}s"

    def get_tool_metrics(self) -> Dict[str, Any]:
        """Retorna métricas agregadas de herramientas."""
        tools_data = {}
        for name, stats in self.tool_stats.items():
            avg_ms = stats["total_ms"] / stats["calls"] if stats["calls"] > 0 else 0
            success_rate = (stats["success"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
            tools_data[name] = {
                **stats,
                "avg_ms": round(avg_ms, 2),
                "success_rate": round(success_rate, 1)
            }
        return tools_data

    def get_skill_metrics(self) -> Dict[str, Any]:
        """Retorna métricas de activación de skills."""
        result = {}
        for skill_id, stats in self.skill_stats.items():
            result[skill_id] = {
                "activations": stats["activations"],
                "last_used": (
                    datetime.fromtimestamp(stats["last_used"]).strftime("%Y-%m-%d %H:%M")
                    if stats["last_used"] else "Nunca"
                )
            }
        return result

    def get_recent_tool_calls(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retorna las últimas N ejecuciones de herramientas."""
        recent = self.tool_history[-limit:]
        # Formatear timestamps
        for entry in recent:
            entry["time_ago"] = self._format_time_ago(entry["timestamp"])
        return list(reversed(recent))

    def get_tools_ranking(self, top: int = 10) -> List[Dict[str, Any]]:
        """Retorna las herramientas más usadas ordenadas por uso."""
        ranking = []
        for name, stats in self.tool_stats.items():
            ranking.append({
                "name": name,
                "calls": stats["calls"],
                "avg_ms": round(stats["total_ms"] / stats["calls"], 2) if stats["calls"] > 0 else 0,
                "success_rate": round(
                    (stats["success"] / stats["calls"] * 100) if stats["calls"] > 0 else 0, 1
                )
            })
        ranking.sort(key=lambda x: x["calls"], reverse=True)
        return ranking[:top]

    def get_full_summary(self) -> Dict[str, Any]:
        """Retorna resumen completo de todas las métricas."""
        total_tool_calls = sum(s["calls"] for s in self.tool_stats.values())
        total_tool_success = sum(s["success"] for s in self.tool_stats.values())
        total_tool_failures = sum(s["failure"] for s in self.tool_stats.values())

        return {
            "uptime": self.get_uptime(),
            "server_start": datetime.fromtimestamp(self.server_start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "tools": {
                "total_calls": total_tool_calls,
                "total_success": total_tool_success,
                "total_failures": total_tool_failures,
                "global_success_rate": round(
                    (total_tool_success / total_tool_calls * 100) if total_tool_calls > 0 else 0, 1
                ),
                "unique_tools_used": len(self.tool_stats),
                "ranking": self.get_tools_ranking(),
                "by_tool": self.get_tool_metrics()
            },
            "skills": {
                "total_activations": sum(s["activations"] for s in self.skill_stats.values()),
                "unique_skills_used": len(self.skill_stats),
                "by_skill": self.get_skill_metrics()
            },
            "documents": {
                "generated_this_session": self.docs_generated,
                "by_type": dict(self.docs_by_type)
            },
            "conversations": {
                "total": self.conversations_count,
                "messages": self.messages_count
            }
        }

    def _format_time_ago(self, timestamp: float) -> str:
        """Formatea un timestamp como 'hace X minutos'."""
        elapsed = time.time() - timestamp
        if elapsed < 60:
            return "Hace unos segundos"
        elif elapsed < 3600:
            minutes = int(elapsed / 60)
            return f"Hace {minutes} min"
        elif elapsed < 86400:
            hours = int(elapsed / 3600)
            return f"Hace {hours}h"
        else:
            days = int(elapsed / 86400)
            return f"Hace {days}d"


# Instancia global singleton
metrics_collector = MetricsCollector()
