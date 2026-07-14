from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class SkillMetadata(BaseModel):
    """Level 1: Metadata cargada en startup"""
    name: str = Field(..., max_length=64)
    description: str = Field(..., min_length=1, max_length=1024)
    compatibility: Optional[str] = Field(None, max_length=500)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    # Nuevos campos sugeridos en Phase 1 de mejoras-skill.md
    ui_icon: Optional[str] = None
    ui_color: Optional[str] = None
    short_description: Optional[str] = Field(None, max_length=150)
    examples: list[str] = Field(default_factory=list)
    
class SkillConfig(BaseModel):
    """Configuración interna del skill"""
    version: str = "1.0"
    permissions: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    ui_icon: Optional[str] = None
    ui_color: Optional[str] = None
