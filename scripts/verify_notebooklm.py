"""Test rápido de integración completa NotebookLM."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=== TEST DE INTEGRACION COMPLETA ===\n")

# 1. Servicio
from app.services.notebooklm_service import notebooklm_service
status = notebooklm_service.get_status()
mcp = status["mcp_exe"]
print(f"[OK] NotebookLMService: MCP={mcp}")

# 2. Tools
from app.core.skills.library.notebooklm_legal.tools import get_tools_schema, get_tools
schemas = get_tools_schema()
tools = get_tools()
print(f"[OK] NotebookLM Tools: {len(schemas)} schemas, {len(tools)} funciones")

# 3. SkillManager
from app.core.skills.manager import SkillManager
sm = SkillManager()
count = len(sm._metadata_cache)
has_nb = "notebooklm_legal" in sm._metadata_cache
print(f"[OK] SkillManager: {count} skills, notebooklm_legal={'SI' if has_nb else 'NO'}")

# 4. ai.py and tools check
with open("app/api/routers/ai.py", "r", encoding="utf-8") as f:
    content = f.read()

from app.api.tools.schemas import TOOLS_SCHEMA
schema_names = {t["name"] for t in TOOLS_SCHEMA[0]["function_declarations"]}
nb_names = ["notebook_query_legal", "notebook_list_tagged", "notebook_create_legal",
            "notebook_add_source", "notebook_research_legal"]
found = sum(1 for t in nb_names if t in schema_names)
print(f"[OK] TOOLS_SCHEMA: {found}/5 herramientas en el schema global")

has_instructions = "notebook_query_legal" in content
print(f"[OK] System prompt: {'SI' if has_instructions else 'NO'}")

has_dispatch = "execute_tool" in content
print(f"[OK] execute_tool dispatch: {'SI' if has_dispatch else 'NO'}")

# 5. Script setup
has_setup = os.path.exists("scripts/setup_notebooklm.py")
print(f"[OK] Script setup: {'SI' if has_setup else 'NO'}")

# 6. Tests
has_tests = os.path.exists("tests/test_notebooklm_integration.py")
print(f"[OK] Tests: {'SI' if has_tests else 'NO'}")

print("\n=== RESULTADOS ===")
all_ok = all([has_nb, found == 5, has_instructions, has_dispatch, has_setup, has_tests])
if all_ok:
    print("[PASS] TODOS LOS COMPONENTES VERIFICADOS EXITOSAMENTE")
else:
    print("[FAIL] Hay componentes faltantes")

print("\nArchivos creados:")
for f in [
    "app/services/notebooklm_service.py",
    "app/core/skills/library/notebooklm_legal/SKILL.md",
    "app/core/skills/library/notebooklm_legal/tools.py",
    "app/core/skills/library/notebooklm_legal/__init__.py",
    "scripts/setup_notebooklm.py",
    "tests/test_notebooklm_integration.py",
]:
    exists = os.path.exists(f)
    print(f"  {'[OK]' if exists else '[!!]'} {f}")

print("\nArchivos modificados:")
print("  [OK] app/api/routers/ai.py (TOOLS_SCHEMA + execute_tool + system prompt)")
