import yaml
import os
import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import validate_call, ValidationError

from .base import SkillMetadata, SkillConfig
from app.core.skills.autogenerador_schemas import generar_gemini_schema_de_funcion

logger = logging.getLogger(__name__)

class SkillManager:
    """
    Gestor de Skills con Progressive Disclosure
    
    Level 1: Metadata (startup / on_demand reload)
    Level 2: Instrucciones completas (on-demand con cache)
    Level 3: Recursos externos (when needed)
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SkillManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, skills_dir: str = "app/core/skills/library"):
        if getattr(self, "_initialized", False):
            return
            
        self.skills_dir = Path(skills_dir)
        self._metadata_cache: dict[str, SkillMetadata] = {}
        self._instructions_cache: dict[str, str] = {}
        self._tools_cache: dict[str, dict] = {}
        self._tool_to_skill_map: dict[str, str] = {}
        self._last_loaded = 0.0
        self._load_all_metadata()
        self._initialized = True
        
    def _check_hot_reload(self):
        """Verifica si algún archivo SKILL.md o configuración cambió para recargar"""
        if not self.skills_dir.exists():
            return
            
        needs_reload = False
        latest_mtime = getattr(self, "_last_loaded", 0.0)
        
        for skill_folder in self.skills_dir.iterdir():
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if skill_file.exists():
                    mtime = skill_file.stat().st_mtime
                    if mtime > latest_mtime:
                        needs_reload = True
                        break
                        
        if needs_reload:
            logger.info("Cambios detectados en skills. Recargando en caliente...")
            self._load_all_metadata()

    def _load_all_metadata(self):
        """Level 1: Carga metadata de todos los skills"""
        if not self.skills_dir.exists():
            logger.warning(f"El directorio de skills no existe: {self.skills_dir}")
            return
            
        new_metadata_cache = {}
        # Clear instructions cache since we are reloading
        self._instructions_cache.clear()
        self._last_loaded = time.time()
        
        for skill_folder in self.skills_dir.iterdir():
            if skill_folder.is_dir():
                skill_file = skill_folder / "SKILL.md"
                if skill_file.exists():
                    try:
                        metadata = self._parse_skill_metadata(skill_file)
                        new_metadata_cache[skill_folder.name] = metadata
                    except Exception as e:
                        logger.error(f"Error cargando metadatos para {skill_folder.name}: {e}")
                        
        self._metadata_cache = new_metadata_cache
        self._preload_all_tools()

    def _preload_all_tools(self):
        """Importa dinámicamente y almacena en caché las herramientas de todos los skills"""
        import importlib
        new_tools_cache = {}
        new_tool_to_skill_map = {}
        
        for skill_id in self._metadata_cache.keys():
            tools_module = f"app.core.skills.library.{skill_id}.tools"
            try:
                module = importlib.import_module(tools_module)
                # Recarga en caliente para reflejar cambios sin reiniciar
                importlib.reload(module)
                
                funcs = getattr(module, "get_tools", lambda: [])()
                raw_schemas = getattr(module, "get_tools_schema", lambda: [])()
                
                # Si no hay esquemas manuales definidos pero sí hay funciones, los autogeneramos dinámicamente
                if not raw_schemas and funcs:
                    raw_schemas = [generar_gemini_schema_de_funcion(func) for func in funcs]
                
                sanitized_schemas = [
                    self._sanitize_gemini_schema(schema) for schema in raw_schemas
                ]
                
                new_tools_cache[skill_id] = {
                    "funcs": funcs,
                    "schema": sanitized_schemas
                }
                
                for func in funcs:
                    func_name = getattr(func, "__name__", None)
                    if func_name:
                        new_tool_to_skill_map[func_name] = skill_id
                        
                logger.info(f"Pre-cargadas {len(funcs)} herramientas para el skill '{skill_id}'")
            except ImportError as e:
                # No todos los skills tienen necesariamente herramientas
                logger.debug(f"No se pudieron importar herramientas para el skill '{skill_id}': {e}")
                new_tools_cache[skill_id] = {"funcs": [], "schema": []}
            except Exception as e:
                logger.error(f"Error precargando herramientas para {skill_id}: {e}")
                new_tools_cache[skill_id] = {"funcs": [], "schema": []}
                
        self._tools_cache = new_tools_cache
        self._tool_to_skill_map = new_tool_to_skill_map
    
    def _parse_skill_metadata(self, file_path: Path) -> SkillMetadata:
        """Parsea el frontmatter YAML del SKILL.md y valida con Pydantic"""
        content = file_path.read_text(encoding="utf-8")
        
        if content.startswith("---"):
            end_index = content.find("---", 3)
            if end_index != -1:
                yaml_content = content[3:end_index].strip()
                data = yaml.safe_load(yaml_content)
                # Pydantic validation handles parsing and errors implicitly
                return SkillMetadata(**data)
        
        raise ValueError(f"SKILL.md sin frontmatter válido: {file_path}")
    
    def list_available_skills(self) -> dict[str, SkillMetadata]:
        """Level 1: Retorna metadata de todos los skills"""
        self._check_hot_reload()
        return self._metadata_cache.copy()
    
    def get_skill_instructions(self, skill_id: str) -> Optional[str]:
        """Level 2: Carga instrucciones completas en cache"""
        self._check_hot_reload()
        
        if skill_id in self._instructions_cache:
            return self._instructions_cache[skill_id]
            
        skill_file = self.skills_dir / skill_id / "SKILL.md"
        
        if not skill_file.exists():
            return None
        
        content = skill_file.read_text(encoding="utf-8")
        
        instructions = content
        if content.startswith("---"):
            end_index = content.find("---", 3)
            if end_index != -1:
                instructions = content[end_index + 3:].strip()
                
        self._instructions_cache[skill_id] = instructions
        return instructions
    
    def get_skill_resource(self, skill_id: str, resource_path: str) -> Optional[str]:
        """Level 3: Carga recurso específico on-demand"""
        self._check_hot_reload()
        resource_file = self.skills_dir / skill_id / resource_path
        
        if not resource_file.exists():
            return None
        
        return resource_file.read_text(encoding="utf-8")
    
    @staticmethod
    def _sanitize_gemini_schema(schema: dict, is_properties_dict: bool = False) -> dict:
        """
        Sanitiza un JSON Schema generado por Pydantic para hacerlo compatible con Gemini API.
        
        Gemini Function Calling NO soporta estos campos estándar de JSON Schema:
        - additionalProperties
        - title
        - $defs / definitions
        - default
        - anyOf / oneOf / allOf
        - examples
        
        Esta función los elimina recursivamente.
        """
        # Campos que Gemini API no reconoce
        CAMPOS_NO_SOPORTADOS = {
            'additionalProperties', 'title', '$defs', 'definitions',
            'default', 'anyOf', 'oneOf', 'allOf', 'examples', '$schema',
            'discriminator'
        }
        
        if not isinstance(schema, dict):
            return schema
        
        # Crear copia limpia sin los campos prohibidos
        limpio = {}
        for key, value in schema.items():
            if key in CAMPOS_NO_SOPORTADOS and not is_properties_dict:
                continue
            
            if isinstance(value, dict):
                limpio[key] = SkillManager._sanitize_gemini_schema(value, is_properties_dict=(key == 'properties'))
            elif isinstance(value, list):
                limpio[key] = [
                    SkillManager._sanitize_gemini_schema(item, is_properties_dict=False) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                # Convertir tipos Python a tipos Gemini (mayúsculas)
                if key == 'type' and isinstance(value, str):
                    type_map = {
                        'string': 'STRING', 'integer': 'INTEGER', 'number': 'NUMBER',
                        'boolean': 'BOOLEAN', 'array': 'ARRAY', 'object': 'OBJECT'
                    }
                    limpio[key] = type_map.get(value.lower(), value.upper())
                else:
                    limpio[key] = value
        
        return limpio

    def get_skill_tools(self, skill_id: str):
        """Obtiene las herramientas del skill desde la caché precargada."""
        self._check_hot_reload()
        return self._tools_cache.get(skill_id, {"funcs": [], "schema": []})
    
    def get_system_prompt_with_skills(self, base_prompt: str, skill_id: Optional[str] = None) -> str:
        """Fusiona el prompt base con instrucciones del skill activo"""
        if not skill_id:
            return base_prompt
        
        instructions = self.get_skill_instructions(skill_id)
        if not instructions:
            return base_prompt
        
        return f"{base_prompt}\n\n## MODO DE OPERACIÓN ACTIVO: {skill_id.upper()}\n{instructions}"
    
    def discover_skills_runtime(self):
        """Recargar skills en caliente manualmente"""
        self._load_all_metadata()

    def get_skill_config(self, skill_id: str) -> SkillConfig:
        """Obtiene la configuración (ej. permisos) desde la metadata."""
        self._check_hot_reload()
        metadata = self._metadata_cache.get(skill_id)
        if not metadata or not metadata.metadata:
            return SkillConfig()
        return SkillConfig(**metadata.metadata)

    def validate_skill_tools(self, skill_id: str) -> dict:
        """Valida que un skill tenga tools correctamente implementados"""
        tools = self.get_skill_tools(skill_id)
        
        validation = {
            "has_tools": len(tools["funcs"]) > 0,
            "has_schema": len(tools["schema"]) > 0,
            "tools_count": len(tools["funcs"]),
            "schema_valid": True,
            "errors": []
        }
        
        if len(tools["funcs"]) != len(tools["schema"]):
            validation["schema_valid"] = False
            validation["errors"].append("Mismatch entre número de tools y schemas")
            
        return validation

    def register_global_tools(self, tools_module):
        """Registra herramientas disponibles para todos los skills de forma transversal."""
        self.global_tools = {
            "calculadora_liquidacion": getattr(tools_module, "calculadora_liquidacion", None),
            "calculadora_terminos": getattr(tools_module, "calculadora_terminos", None),
            "buscador_jurisprudencia": getattr(tools_module, "buscador_jurisprudencia", None)
        }

    async def execute_tool(
        self,
        skill_id: str,
        tool_name: str,
        params: dict,
        user_permissions: list[str],
        db: Optional[AsyncSession] = None
    ) -> Any:
        """Ejecuta un tool perteneciente a un skill validando sus permisos primero."""
        skill_config = self.get_skill_config(skill_id)
        required_perms = skill_config.permissions
        
        if not all(perm in user_permissions for perm in required_perms):
            raise PermissionError(f"Permisos insuficientes para {tool_name}")
            
        tools = self.get_skill_tools(skill_id)
        tool_func = next((f for f in tools["funcs"] if f.__name__ == tool_name), None)
        
        if not tool_func:
            raise ValueError(f"Tool {tool_name} no encontrado en {skill_id}")
            
        try:
            validated_func = validate_call(tool_func)
        except Exception as e:
            logger.warning(f"No se pudo envolver la función {tool_name} con validate_call: {e}")
            validated_func = tool_func
            
        start_time = datetime.now()
        success = False
        result = None
        error_message = None
        try:
            if __import__("asyncio").iscoroutinefunction(tool_func):
                result = await validated_func(**params)
            else:
                result = validated_func(**params)
            success = True
            return result
        except ValidationError as val_err:
            error_message = str(val_err)
            logger.error(f"Error de validación en parámetros de {tool_name}: {error_message}")
            result = {
                "error": "Error de validación de parámetros",
                "detalles": error_message,
                "sugerencia": "Verifica que los tipos y nombres de los campos coincidan estrictamente con el esquema registrado de la herramienta."
            }
            return result
        except Exception as exec_err:
            error_message = str(exec_err)
            logger.error(f"Error ejecutando la herramienta {tool_name}: {error_message}")
            raise
        finally:
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            await self.log_tool_call(
                skill_id, tool_name, params, result, duration_ms, success, error_message, db
            )

    async def log_tool_call(
        self,
        skill_id: str,
        tool_name: str,
        params: dict,
        result: Any,
        duration_ms: float,
        success: bool,
        error_message: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ):
        """Registra la ejecución de tools para auditoría transversal (base de datos o logger)."""
        try:
            params_str = json.dumps(params)
        except Exception:
            params_str = str(params)
            
        try:
            result_str = json.dumps(result)[:2000] if result is not None else None
        except Exception:
            result_str = str(result)[:2000] if result is not None else None

        if db is not None:
            try:
                from app.models.tool_audit import ToolAuditLog
                audit_entry = ToolAuditLog(
                    skill_id=skill_id,
                    tool_name=tool_name,
                    parameters=params_str,
                    result=result_str,
                    duration_ms=duration_ms,
                    success=success,
                    error_message=error_message
                )
                db.add(audit_entry)
                await db.commit()
                logger.debug(f"📜 Registro de auditoría guardado en BD para tool: {tool_name}")
                return
            except Exception as db_err:
                logger.error(f"❌ Error al guardar registro de auditoría en BD: {db_err}. Usando fallback a texto.")
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "skill_id": skill_id,
            "tool_name": tool_name,
            "params": params_str[:500],
            "success": success,
            "duration_ms": duration_ms,
            "error_message": error_message
        }
        logger.info(f"Tool execution: {json.dumps(log_entry)}")
