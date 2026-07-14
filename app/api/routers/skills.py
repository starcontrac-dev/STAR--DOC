from fastapi import APIRouter
from typing import Dict, List, Any
from app.core.skills.manager import SkillManager

router = APIRouter(prefix="/api/skills", tags=["Legal AI Engine"])
skill_manager = SkillManager()

@router.get("/v2")
async def get_categorized_skills() -> Dict[str, List[Dict[str, Any]]]:
    """
    Retorna un catálogo categorizado de skills incluyendo el número de herramientas
    (tools) vinculadas a cada skill.
    """
    skills_meta = skill_manager.list_available_skills()
    categorized_skills = {}
    
    for skill_id, meta in skills_meta.items():
        # Asignar a una categoría leyendo metadata o usando un default
        category = "General"
        if meta.metadata and isinstance(meta.metadata, dict):
            category = meta.metadata.get("category", "General")
        
        # Validar y obtener count de tools
        validation = skill_manager.validate_skill_tools(skill_id)
        
        skill_data = {
            "id": skill_id,
            "name": meta.name,
            "description": meta.description,
            "ui_icon": getattr(meta, "ui_icon", None),
            "ui_color": getattr(meta, "ui_color", None),
            "short_description": getattr(meta, "short_description", None),
            "examples": getattr(meta, "examples", []),
            "tools_count": validation.get("tools_count", 0),
            "permissions": meta.metadata.get("permissions", []) if meta.metadata and isinstance(meta.metadata, dict) else []
        }
        
        if category not in categorized_skills:
            categorized_skills[category] = []
            
        categorized_skills[category].append(skill_data)
        
    return categorized_skills
