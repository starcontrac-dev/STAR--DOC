"""
Script para etiquetar los cuadernos juridicos que ya se crearon.
Los cuadernos existen pero no se les pudo asignar tags porque
fallo la extraccion del notebook_id.
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.notebooklm_service import notebooklm_service, TAG_LEGAL_ROOT

# IDs extraidos de la salida del setup anterior
NOTEBOOKS_CREADOS = [
    {"id": "639c3c10-943e-4781-9296-3ecd0ff46a02", "area": "constitucional", "tag": "#legal-constitucional"},
    {"id": "f083dce1-5c10-4104-a916-b4b813ae93d0", "area": "administrativo", "tag": "#legal-administrativo"},
    {"id": "ad92100a-637f-467d-8147-92d740952130", "area": "comercial", "tag": "#legal-comercial"},
    {"id": "addac981-6324-459e-b5ff-d7c0780aa68b", "area": "civil", "tag": "#legal-civil"},
    {"id": "8fb94011-af54-47b0-8e0b-94d814d4f5e7", "area": "tributario", "tag": "#legal-tributario"},
    {"id": "1edae526-46d4-4efe-bc50-50c36c474cae", "area": "crypto", "tag": "#legal-crypto"},
]

# URLs de fuentes que deben asociarse
FUENTES = {
    "639c3c10-943e-4781-9296-3ecd0ff46a02": ["https://www.corteconstitucional.gov.co/relatoria/"],
    "f083dce1-5c10-4104-a916-b4b813ae93d0": ["https://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html"],
    "ad92100a-637f-467d-8147-92d740952130": ["https://www.secretariasenado.gov.co/senado/basedoc/ley_1258_2008.html"],
    "8fb94011-af54-47b0-8e0b-94d814d4f5e7": ["https://www.secretariasenado.gov.co/senado/basedoc/estatuto_tributario.html"],
}


async def fix_tags_and_sources():
    """Aplica tags a los cuadernos existentes y agrega fuentes faltantes."""
    print("=" * 60)
    print(" Reparando etiquetas y fuentes")
    print("=" * 60)

    for nb in NOTEBOOKS_CREADOS:
        nb_id = nb["id"]
        tags_str = f"{TAG_LEGAL_ROOT},{nb['tag']}"

        # 1. Aplicar etiquetas
        print(f"\n[TAG] {nb['area']}: {nb_id[:12]}...")
        tag_result = await notebooklm_service.tag_notebook(nb_id, tags_str)
        tag_str = json.dumps(tag_result, ensure_ascii=False, default=str)
        print(f"      -> {tag_str[:200]}")

        # 2. Agregar fuentes si corresponde
        if nb_id in FUENTES:
            for url in FUENTES[nb_id]:
                print(f"[SRC] Agregando: {url[:60]}")
                src_result = await notebooklm_service.add_url_source(nb_id, url)
                src_str = json.dumps(src_result, ensure_ascii=False, default=str)
                print(f"      -> {src_str[:200]}")
        
        await asyncio.sleep(1)

    # Verificar resultado
    print("\n" + "=" * 60)
    print(" Verificacion final: listando cuadernos")
    print("=" * 60)
    
    result = await notebooklm_service.list_notebooks()
    result_str = json.dumps(result, ensure_ascii=False, default=str, indent=2)
    print(result_str[:2000])

    # Buscar por tag #legal
    print("\n--- Buscando por tag #legal ---")
    tagged = await notebooklm_service.search_by_tag("#legal")
    tagged_str = json.dumps(tagged, ensure_ascii=False, default=str, indent=2)
    print(tagged_str[:2000])


if __name__ == "__main__":
    asyncio.run(fix_tags_and_sources())
