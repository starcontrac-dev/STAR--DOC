from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
import os
from app.core.config import settings
import platform
import shutil

async def get_total_users(db: AsyncSession) -> int:
    try:
        result = await db.execute(select(func.count()).select_from(User))
        return result.scalar() or 0
    except Exception:
        return 0

# Placeholder for active users logic (e.g. login within last 7 days)
# Since we don't track last_login yet, returning total or a subset
async def get_active_users(db: AsyncSession) -> int:
    return await get_total_users(db)

async def get_document_activity():
    try:
        if not os.path.exists(settings.OUTPUT_DIR):
            return 0
        output_files = [f for f in os.listdir(settings.OUTPUT_DIR) if os.path.isfile(os.path.join(settings.OUTPUT_DIR, f))]
        # We could group by date here if needed
        return len(output_files)
    except Exception:
        return 0

from app.services.template_manager import TemplateManager

async def get_template_usage(db: AsyncSession):
    """
    Calculates template usage based on files in the output directory.
    Matches filename prefixes with known template names.
    """
    usage_stats = {}
    
    # Get all available templates
    try:
        templates_list = await TemplateManager.get_all_templates_from_db(db) # ['Template1.docx', 'Template2.md', ...]
        # Normalize to basenames without extension for matching
        template_basenames = {t: os.path.splitext(t)[0] for t in templates_list}
        
        # Initialize stats with 0 for all templates (or empty if we only want active ones)
        # usage_stats = {name: 0 for name in template_basenames.values()} 
        
        if not os.path.exists(settings.OUTPUT_DIR):
            return {}

        output_files = [f for f in os.listdir(settings.OUTPUT_DIR) if os.path.isfile(os.path.join(settings.OUTPUT_DIR, f))]
        
        for filename in output_files:
            # Simple heuristic: Check if output filename starts with a template basename
            # Sort templates by length desc to match longest name first (e.g. "Carta" vs "Carta de Despido")
            sorted_basenames = sorted(template_basenames.values(), key=len, reverse=True)
            
            matched = False
            for basename in sorted_basenames:
                if filename.startswith(basename):
                    usage_stats[basename] = usage_stats.get(basename, 0) + 1
                    matched = True
                    break
            
            if not matched:
                # categorize as "Otros" or "Temp"
                if filename.startswith("temp_"):
                    usage_stats["Borradores/Temporales"] = usage_stats.get("Borradores/Temporales", 0) + 1
                else:
                    usage_stats["Otros"] = usage_stats.get("Otros", 0) + 1

    except Exception as e:
        print(f"Error calculating usage stats: {e}")
        return {"Error": 1}

    # Sort by usage desc and take top 5 + Others
    sorted_stats = dict(sorted(usage_stats.items(), key=lambda item: item[1], reverse=True))
    return sorted_stats


async def get_activity_history(days: int = 14):
    """
    Returns document generation counts for the last 'days' days.
    """
    try:
        from datetime import datetime, timedelta
        
        history = {}
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
        dates.reverse() # Oldest first
        
        # Initialize with 0
        for d in dates:
            history[d] = 0
            
        if os.path.exists(settings.OUTPUT_DIR):
            for f in os.listdir(settings.OUTPUT_DIR):
                path = os.path.join(settings.OUTPUT_DIR, f)
                if os.path.isfile(path):
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(path))
                        date_str = mtime.strftime("%Y-%m-%d")
                        if date_str in history:
                            history[date_str] += 1
                    except Exception:
                        continue # Skip bad files
        
        return {
            "labels": dates,
            "data": [history[d] for d in dates]
        }
    except Exception as e:
        print(f"Error in activity history: {e}")
        return {"labels": [], "data": []}

async def get_hourly_activity():
    """
    Returns document generation distribution by hour of day (0-23).
    """
    try:
        from datetime import datetime
        hours = [0] * 24
        if os.path.exists(settings.OUTPUT_DIR):
            for f in os.listdir(settings.OUTPUT_DIR):
                path = os.path.join(settings.OUTPUT_DIR, f)
                if os.path.isfile(path):
                    try:
                        mtime = datetime.fromtimestamp(os.path.getmtime(path))
                        hours[mtime.hour] += 1
                    except Exception:
                        continue
        return hours
    except Exception as e:
        print(f"Error in hourly activity: {e}")
        return [0] * 24

async def get_storage_distribution():
    """
    Returns storage usage in MB for Output (Docs) vs Templates.
    """
    def get_dir_size(start_path = '.'):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(start_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                # skip if it is symbolic link
                if not os.path.islink(fp):
                    try:
                        total_size += os.path.getsize(fp)
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
        return total_size

    docs_size = get_dir_size(settings.OUTPUT_DIR) if os.path.exists(settings.OUTPUT_DIR) else 0
    templates_size = get_dir_size(settings.PLANTILLAS_DIR) if os.path.exists(settings.PLANTILLAS_DIR) else 0
    
    # Convert to MB
    return {
        "docs_mb": round(docs_size / (1024 * 1024), 2),
        "templates_mb": round(templates_size / (1024 * 1024), 2)
    }

async def get_system_health():
    # Check Disk Space
    try:
        total, used, free = shutil.disk_usage(os.getcwd())
        disk_usage_percent = (used / total) * 100
        disk_usage_str = f"{disk_usage_percent:.1f}%"
    except Exception:
        disk_usage_str = "N/A"
    
    return {
        "status": "healthy",
        "database": "connected", # Assumed if we are here
        "disk_usage": disk_usage_str,
        "platform": platform.system()
    }
