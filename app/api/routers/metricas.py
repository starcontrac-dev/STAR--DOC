"""
Router de Métricas — Endpoints REST para el dashboard de STAR-DOC.

Provee datos reales del sistema:
- Métricas de IA (AIService): tokens, latencia, costos, circuit breakers
- Métricas de Tools (MetricsCollector): uso, ranking, historial
- Métricas de Skills: activaciones por skill
- Métricas de Sistema: CPU, RAM, disco, uptime
- Métricas de Documentos: conteos del filesystem
- Métricas de Usuario: datos de BD (users, etc.)

Todos los endpoints requieren autenticación.
Los endpoints admin requieren is_admin=True O username='starcontract'.
"""
import os
import time
import platform
import shutil
import logging
import psutil
import json
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_session
from app.auth import get_current_active_user
from app.models.user import User, UserRole
from app.core.config import settings
from app.services.ai_service import ai_service
from app.services.metrics_collector import metrics_collector
from app.core.skills.manager import SkillManager
from app.core.redis_client import redis_manager
from app.core.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metricas", tags=["Data & Metrics"])

# --- Helpers de Autorización ---

def _is_admin(user: User) -> bool:
    """Verifica si el usuario es administrador (por rol O por username)."""
    is_role_admin = getattr(user, 'role', None) in ("admin", UserRole.ADMIN, UserRole.ADMIN.value)
    is_username_admin = user.username == "starcontract"
    is_flag_admin = getattr(user, 'is_admin', False)
    return is_role_admin or is_username_admin or is_flag_admin


# ============================================================
# ENDPOINT 1: Resumen General del Usuario
# ============================================================

@router.get("/resumen")
async def get_resumen_metricas(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna métricas generales del usuario actual.
    Accesible por cualquier usuario autenticado.
    """
    # Documentos generados (del filesystem)
    doc_count = 0
    try:
        if os.path.exists(settings.OUTPUT_DIR):
            doc_count = len([
                f for f in os.listdir(settings.OUTPUT_DIR)
                if os.path.isfile(os.path.join(settings.OUTPUT_DIR, f))
            ])
    except Exception:
        pass

    # Plantillas disponibles
    template_count = 0
    try:
        if os.path.exists(settings.PLANTILLAS_DIR):
            template_count = len([
                f for f in os.listdir(settings.PLANTILLAS_DIR)
                if f.endswith(('.docx', '.md', '.txt'))
            ])
    except Exception:
        pass

    # Tiempo ahorrado estimado (20 min por documento)
    time_saved_min = doc_count * 20
    time_saved_display = f"{time_saved_min / 60:.1f} horas" if time_saved_min > 60 else f"{time_saved_min} min"

    return {
        "usuario": current_user.username,
        "documentos_generados": doc_count,
        "plantillas_disponibles": template_count,
        "tiempo_ahorrado": time_saved_display,
        "uptime_servidor": metrics_collector.get_uptime(),
        "es_admin": _is_admin(current_user)
    }


# ============================================================
# ENDPOINT 2: Métricas de IA (Solo Admin)
# ============================================================

@router.get("/ia")
async def get_metricas_ia(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna métricas detalladas del servicio de IA (Gemini).
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    ai_metrics = ai_service.get_detailed_metrics()

    # Enriquecer con datos del historial reciente
    now = time.time()
    history = ai_service.request_history

    # Calcular throughput (requests por minuto en los últimos 5 min)
    recent_5min = [r for r in history if now - r["timestamp"] < 300]
    throughput = len(recent_5min) / 5 if recent_5min else 0

    # Latencias percentiles
    latencies = [r["latency_ms"] for r in history if r["success"]]
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    ai_metrics["throughput_rpm"] = round(throughput, 2)
    ai_metrics["latency_percentiles"] = {
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2)
    }
    ai_metrics["history_size"] = len(history)

    return ai_metrics


# ============================================================
# ENDPOINT 3: Métricas de Herramientas / Tools (Solo Admin)
# ============================================================

@router.get("/tools")
async def get_metricas_tools(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna métricas de uso de herramientas (tools) del sistema.
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    # Intentar obtener métricas acumuladas desde Redis
    try:
        from app.services.redis_metrics import RedisMetrics
        ranking = await RedisMetrics.get_tools_ranking(top=15)
        if ranking:
            by_tool = {}
            for item in ranking:
                name = item["name"]
                stats = await RedisMetrics.get_tool_metrics(name)
                avg_ms = stats["total_ms"] / stats["calls"] if stats["calls"] > 0 else 0
                success_rate = (stats["success"] / stats["calls"] * 100) if stats["calls"] > 0 else 0
                by_tool[name] = {
                    **stats,
                    "avg_ms": round(avg_ms, 2),
                    "success_rate": round(success_rate, 1)
                }
            
            # Obtener historial reciente de Redis
            pool = await redis_manager.get_pool(db=3)
            recent_raw = await pool.lrange("metrics:tool_history", 0, 24)  # type: ignore[misc]
            recent_calls = []
            for r in recent_raw:
                try:
                    entry = json.loads(r)
                    entry["time_ago"] = metrics_collector._format_time_ago(entry["timestamp"])
                    entry["skill"] = entry.get("skill", "global")
                    entry["params"] = entry.get("params", "")
                    recent_calls.append(entry)
                except Exception:
                    pass
            
            total_calls = sum(item["calls"] for item in ranking)
            
            return {
                "ranking": ranking,
                "by_tool": by_tool,
                "recent_calls": recent_calls,
                "total_calls": total_calls
            }
    except Exception as e:
        logger.warning(f"Error al obtener métricas de herramientas desde Redis: {e}")

    # Fallback a memoria volátil local
    return {
        "ranking": metrics_collector.get_tools_ranking(top=15),
        "by_tool": metrics_collector.get_tool_metrics(),
        "recent_calls": metrics_collector.get_recent_tool_calls(limit=25),
        "total_calls": sum(s["calls"] for s in metrics_collector.tool_stats.values()),
    }


# ============================================================
# ENDPOINT 4: Métricas de Skills (Solo Admin)
# ============================================================

@router.get("/skills")
async def get_metricas_skills(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna métricas de uso de skills y su estado de validación.
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    sm = SkillManager()
    available_skills = sm.list_available_skills()

    skills_info = []
    for skill_id, metadata in available_skills.items():
        # Validar herramientas de cada skill
        validation = sm.validate_skill_tools(skill_id)
        # Estadísticas de uso del colector
        usage = metrics_collector.skill_stats.get(skill_id, {"activations": 0, "last_used": None})

        skills_info.append({
            "id": skill_id,
            "name": metadata.name,
            "description": metadata.description,
            "version": getattr(metadata, 'version', '1.0'),
            "tools_count": validation["tools_count"],
            "schema_valid": validation["schema_valid"],
            "activations": usage["activations"],
            "last_used": (
                datetime.fromtimestamp(usage["last_used"]).strftime("%Y-%m-%d %H:%M")
                if usage.get("last_used") else "Nunca"
            ),
            "errors": validation.get("errors", [])
        })

    return {
        "total_skills": len(skills_info),
        "skills": skills_info,
        "global_activations": sum(s["activations"] for s in metrics_collector.skill_stats.values())
    }


# ============================================================
# ENDPOINT 5: Métricas del Sistema (Solo Admin)
# ============================================================

@router.get("/sistema")
async def get_metricas_sistema(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna métricas del sistema operativo y hardware.
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    # CPU
    cpu_percent = psutil.cpu_percent(interval=0.5)
    cpu_count = psutil.cpu_count()

    # Memoria RAM
    mem = psutil.virtual_memory()

    # Disco
    try:
        total, used, free = shutil.disk_usage(os.getcwd())
    except Exception:
        total, used, free = 1, 0, 1

    # Tamaño de directorios del proyecto
    def get_dir_size_mb(path: str) -> float:
        total_size = 0
        if os.path.exists(path):
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        if not os.path.islink(fp):
                            total_size += os.path.getsize(fp)
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
        return round(total_size / (1024 * 1024), 2)

    output_size = get_dir_size_mb(settings.OUTPUT_DIR)
    plantillas_size = get_dir_size_mb(settings.PLANTILLAS_DIR)

    # Proceso Python actual
    process = psutil.Process()
    proc_mem = process.memory_info()

    return {
        "uptime": metrics_collector.get_uptime(),
        "server_start": datetime.fromtimestamp(metrics_collector.server_start_time).strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "cpu": {
            "percent": cpu_percent,
            "cores": cpu_count
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent": mem.percent
        },
        "disk": {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "percent": round((used / total) * 100, 1)
        },
        "storage": {
            "output_mb": output_size,
            "plantillas_mb": plantillas_size,
            "total_mb": round(output_size + plantillas_size, 2)
        },
        "process": {
            "rss_mb": round(proc_mem.rss / (1024**2), 2),
            "vms_mb": round(proc_mem.vms / (1024**2), 2),
            "pid": process.pid
        }
    }


# ============================================================
# ENDPOINT 6: Dashboard Completo (Solo Admin)
# ============================================================

@router.get("/dashboard-completo")
@limiter.limit("30/minute")
async def get_dashboard_completo(
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna TODAS las métricas consolidadas para el dashboard del admin.
    Endpoint principal que alimenta el frontend del dashboard.
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    # Intentar leer de Redis (DB 2)
    try:
        pool = await redis_manager.get_pool(db=2)
        cached = await pool.get("dashboard:completo")
        if cached:
            return json.loads(cached)
    except Exception as ex:
        logger.warning(f"Error al leer caché de dashboard de Redis: {ex}")

    # --- Usuarios de BD ---
    try:
        result = await db.execute(text("SELECT COUNT(*) FROM users"))
        total_users = result.scalar() or 0
    except Exception as e:
        logger.warning(f"Error consultando usuarios: {e}")
        await db.rollback()
        total_users = 0

    try:
        result = await db.execute(text("SELECT COUNT(*) FROM users WHERE role = 'admin'"))
        admin_users = result.scalar() or 0
    except Exception as e:
        logger.warning(f"Error consultando admins: {e}")
        await db.rollback()
        admin_users = 0

    # --- Documentos del filesystem ---
    doc_count = 0
    recent_docs = []
    try:
        if os.path.exists(settings.OUTPUT_DIR):
            files = [f for f in os.listdir(settings.OUTPUT_DIR) if os.path.isfile(os.path.join(settings.OUTPUT_DIR, f))]
            doc_count = len(files)
            files.sort(key=lambda x: os.path.getmtime(os.path.join(settings.OUTPUT_DIR, x)), reverse=True)
            recent_docs = files[:10]
    except Exception:
        pass

    # --- Plantillas ---
    template_count = 0
    try:
        if os.path.exists(settings.PLANTILLAS_DIR):
            template_count = len([
                f for f in os.listdir(settings.PLANTILLAS_DIR)
                if f.endswith(('.docx', '.md', '.txt'))
            ])
    except Exception:
        pass

    # --- Skills ---
    sm = SkillManager()
    skills = sm.list_available_skills()

    # --- Citas (Appointments) ---
    appointments_data = []
    leads_data = []
    try:
        rows = await db.execute(text("""
            SELECT a.id, a.lead_email, a.lead_name, a.appointment_date, a.appointment_time,
                   a.duration_minutes, a.appointment_type, a.reason, a.status,
                   a.meeting_link, a.internal_notes, a.created_by, a.created_at, a.jitsi_room_name
            FROM appointments a
            LEFT JOIN users u ON a.created_by = u.username
            WHERE a.created_by = 'ai_agent'
               OR a.created_by = 'admin_manual'
               OR u.role = 'admin'
               OR a.created_by = :current_username
            ORDER BY a.appointment_date ASC, a.appointment_time ASC
        """), {"current_username": current_user.username})
        for r in rows.fetchall():
            appointments_data.append({
                "id": r[0],
                "lead_email": r[1],
                "lead_name": r[2] or "Sin nombre",
                "date": str(r[3]),
                "time": str(r[4])[:5],  # HH:MM
                "duration": r[5],
                "type": r[6],
                "reason": r[7],
                "status": r[8],
                "meeting_link": r[9],
                "notes": r[10],
                "created_by": r[11],
                "created_at": str(r[12])[:16] if r[12] else None,
                "jitsi_room_name": r[13]
            })
    except Exception as e:
        logger.warning(f"Error consultando appointments: {e}")
        await db.rollback()

    try:
        rows = await db.execute(text("""
            SELECT id, email, name, phone, service_interest, status, source, created_at
            FROM leads ORDER BY created_at DESC
        """))
        for r in rows.fetchall():
            leads_data.append({
                "id": r[0],
                "email": r[1],
                "name": r[2] or "Sin nombre",
                "phone": r[3],
                "service_interest": r[4],
                "status": r[5],
                "source": r[6],
                "created_at": str(r[7])[:16] if r[7] else None
            })
    except Exception as e:
        logger.warning(f"Error consultando leads: {e}")
        await db.rollback()

    # Calcular uso de disco de forma segura
    try:
        total_d, used_d, free_d = shutil.disk_usage(os.getcwd())
        disk_pct = round((used_d / total_d) * 100, 1)
    except Exception:
        disk_pct = 0.0

    # --- Consolidar ---
    result = {
        "timestamp": datetime.now().isoformat(),
        "usuario": current_user.username,
        "usuarios": {
            "total": total_users,
            "admins": admin_users
        },
        "documentos": {
            "total_generados": doc_count,
            "recientes": recent_docs,
            "plantillas_activas": template_count
        },
        "ia": ai_service.get_detailed_metrics(),
        "tools": metrics_collector.get_full_summary()["tools"],
        "skills": {
            "total_disponibles": len(skills),
            "nombres": list(skills.keys()),
            "usage": metrics_collector.get_skill_metrics()
        },
        "appointments": {
            "total": len(appointments_data),
            "pending": len([a for a in appointments_data if a["status"] == "pending"]),
            "confirmed": len([a for a in appointments_data if a["status"] == "confirmed"]),
            "completed": len([a for a in appointments_data if a["status"] == "completed"]),
            "list": appointments_data
        },
        "leads": {
            "total": len(leads_data),
            "list": leads_data
        },
        "sistema": {
            "uptime": metrics_collector.get_uptime(),
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": disk_pct,
            "python": platform.python_version(),
            "platform": platform.system()
        }
    }

    # Guardar en Redis
    try:
        pool = await redis_manager.get_pool(db=2)
        await pool.setex("dashboard:completo", 30, json.dumps(result, default=str))
    except Exception as ex:
        logger.warning(f"Error al guardar caché de dashboard en Redis: {ex}")

    return result


# ============================================================
# ENDPOINT 7: Citas / Appointments (Solo Admin)
# ============================================================

@router.get("/appointments")
async def get_appointments(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna todas las citas agendadas con datos completos.
    Solo accesible por el administrador.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado: solo administrador")

    appointments = []
    try:
        rows = await db.execute(text("""
            SELECT a.id, a.lead_email, a.lead_name, a.appointment_date, a.appointment_time,
                   a.duration_minutes, a.appointment_type, a.reason, a.status,
                   a.meeting_link, a.internal_notes, a.created_by, a.created_at,
                   l.name as lead_full_name, l.phone as lead_phone, l.service_interest,
                   a.jitsi_room_name
            FROM appointments a
            LEFT JOIN leads l ON a.lead_id = l.id
            LEFT JOIN users u ON a.created_by = u.username
            WHERE a.created_by = 'ai_agent'
               OR a.created_by = 'admin_manual'
               OR u.role = 'admin'
               OR a.created_by = :current_username
            ORDER BY a.appointment_date ASC, a.appointment_time ASC
        """), {"current_username": current_user.username})
        for r in rows.fetchall():
            appointments.append({
                "id": r[0],
                "lead_email": r[1],
                "lead_name": r[2] or r[13] or "Sin nombre",
                "date": str(r[3]),
                "time": str(r[4])[:5],
                "duration": r[5],
                "type": r[6],
                "reason": r[7],
                "status": r[8],
                "meeting_link": r[9],
                "notes": r[10],
                "created_by": r[11],
                "created_at": str(r[12])[:16] if r[12] else None,
                "lead_phone": r[14],
                "service_interest": r[15],
                "jitsi_room_name": r[16]
            })
    except Exception as e:
        logger.error(f"Error consultando appointments: {e}")

    return {
        "total": len(appointments),
        "pending": len([a for a in appointments if a["status"] == "pending"]),
        "confirmed": len([a for a in appointments if a["status"] == "confirmed"]),
        "completed": len([a for a in appointments if a["status"] == "completed"]),
        "appointments": appointments
    }

