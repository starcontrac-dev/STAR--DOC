"""Test rapido de busqueda por tag en NotebookLM."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.notebooklm_service import notebooklm_service

async def test():
    print("=== Test: Buscar cuadernos por tag #legal ===")
    result = await notebooklm_service.search_by_tag("#legal")
    count = result.get("count", 0)
    print(f"Notebooks con #legal: {count}")
    for nb in result.get("notebooks", []):
        title = nb.get("title", "?")
        src = nb.get("source_count", 0)
        nb_id = nb.get("id", "??")[:12]
        print(f"  - {title} (sources={src}, id={nb_id}...)")
    
    print()
    print("=== Test: Buscar por #legal-constitucional ===")
    result2 = await notebooklm_service.search_by_tag("#legal-constitucional")
    count2 = result2.get("count", 0)
    print(f"Notebooks constitucionales: {count2}")
    for nb in result2.get("notebooks", []):
        title = nb.get("title", "?")
        nb_id = nb.get("id", "??")[:12]
        print(f"  - {title} (id={nb_id}...)")

    print()
    print("=== Test: Buscar por #legal-comercial ===")
    result3 = await notebooklm_service.search_by_tag("#legal-comercial")
    count3 = result3.get("count", 0)
    print(f"Notebooks comerciales: {count3}")
    
    print()
    print(f"TOTAL: {count} notebooks juridicos organizados en NotebookLM")

asyncio.run(test())
