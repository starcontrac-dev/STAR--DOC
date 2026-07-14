"""
Script de Setup: Creacion de Cuadernos Juridicos Base para STAR-DOC.

Inicializa la base de conocimiento juridico en NotebookLM
creando los cuadernos fundamentales con las etiquetas de la taxonomia #legal.

Uso: python scripts/setup_notebooklm.py
"""

import asyncio
import json
import sys
import os

# Asegurar path del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.notebooklm_service import notebooklm_service, LEGAL_TAGS


# ──────────────────────────────────────────────────────────
# DEFINICION DE CUADERNOS JURIDICOS BASE
# ──────────────────────────────────────────────────────────

NOTEBOOKS_BASE = [
    {
        "titulo": "Jurisprudencia Constitucional - Tutela y Derechos Fundamentales",
        "area_legal": "constitucional",
        "fuentes_urls": [
            "https://www.corteconstitucional.gov.co/relatoria/",
        ],
        "descripcion": "Sentencias de tutela, derechos fundamentales, constitucionalidad"
    },
    {
        "titulo": "Derecho Administrativo - Contratacion Estatal y Nulidad",
        "area_legal": "administrativo",
        "fuentes_urls": [
            "https://www.secretariasenado.gov.co/senado/basedoc/ley_0080_1993.html",
        ],
        "descripcion": "Contratacion estatal, reparacion directa, nulidad y restablecimiento"
    },
    {
        "titulo": "Derecho Comercial - Sociedades SAS y Contratos Mercantiles",
        "area_legal": "comercial",
        "fuentes_urls": [
            "https://www.secretariasenado.gov.co/senado/basedoc/ley_1258_2008.html",
        ],
        "descripcion": "Ley SAS, contratos mercantiles, insolvencia, propiedad industrial"
    },
    {
        "titulo": "Derecho Civil - Contratos y Obligaciones",
        "area_legal": "civil",
        "fuentes_urls": [],
        "descripcion": "Codigo Civil, contratos, responsabilidad, bienes"
    },
    {
        "titulo": "Derecho Tributario - Estatuto Tributario Colombia",
        "area_legal": "tributario",
        "fuentes_urls": [
            "https://www.secretariasenado.gov.co/senado/basedoc/estatuto_tributario.html",
        ],
        "descripcion": "Renta, IVA, ICA, retenciones, regimen simple"
    },
    {
        "titulo": "Criptoactivos y Fintech - Marco Regulatorio Colombia",
        "area_legal": "crypto",
        "fuentes_urls": [],
        "descripcion": "Regulacion SFC/DIAN, prevencion lavado, tributacion cripto"
    },
]


async def setup_notebooks():
    """Crea todos los cuadernos juridicos base."""
    print("=" * 60)
    print(" STAR-DOC - Setup de Base de Conocimiento Juridico")
    print(" NotebookLM Legal Integration")
    print("=" * 60)
    print()

    # Verificar estado del servicio
    status = notebooklm_service.get_status()
    print(f"MCP Ejecutable: {status['mcp_exe']}")
    print(f"MCP SDK: {status['mcp_sdk']}")
    print(f"Libreria local: {'SI' if status['library_exists'] else 'NO'}")
    print(f"Notebooks en cache: {status['cached_notebooks']}")
    print()

    if "NO ENCONTRADO" in str(status["mcp_exe"]):
        print("[ERROR] notebooklm-mcp no encontrado en PATH.")
        print("    Ejecuta: uv tool install notebooklm-mcp")
        print("    Y luego: notebooklm-mcp-auth")
        return

    # Listar notebooks existentes primero
    print("[1/3] Verificando notebooks existentes...")
    try:
        existing = await notebooklm_service.list_notebooks()
        existing_str = json.dumps(existing, ensure_ascii=False, default=str)
        print(f"    Resultado: {existing_str[:400]}")
    except Exception as e:
        print(f"    Error listando: {e}")
    print()

    # Crear cada cuaderno
    print(f"[2/3] Creando {len(NOTEBOOKS_BASE)} cuadernos juridicos...")
    results = []

    for i, nb in enumerate(NOTEBOOKS_BASE, 1):
        print(f"\n  [{i}/{len(NOTEBOOKS_BASE)}] Creando: {nb['titulo']}")
        print(f"    Area: {nb['area_legal']}")
        print(f"    Fuentes: {len(nb['fuentes_urls'])} URLs")

        try:
            result = await notebooklm_service.create_legal_notebook(
                titulo=nb["titulo"],
                area_legal=nb["area_legal"],
                fuentes_urls=nb["fuentes_urls"] if nb["fuentes_urls"] else None
            )
            results.append(result)
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            print(f"    Resultado: {result_str[:300]}")
        except Exception as e:
            error_result = {"error": str(e), "title": nb["titulo"]}
            results.append(error_result)
            print(f"    ERROR: {e}")

        # Pausa entre creaciones para no sobrecargar
        await asyncio.sleep(2)

    # Resumen final
    print("\n" + "=" * 60)
    print(" RESUMEN")
    print("=" * 60)

    exitosos = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    errores = sum(1 for r in results if isinstance(r, dict) and "error" in r)

    print(f"  Exitosos: {exitosos}/{len(NOTEBOOKS_BASE)}")
    print(f"  Errores:  {errores}/{len(NOTEBOOKS_BASE)}")

    for r in results:
        if not isinstance(r, dict):
            print(f"  [??] Resultado inesperado: {str(r)[:60]}")
            continue
        
        if r.get("status") == "success":
            title = r.get("title", "Sin titulo")
            print(f"  [OK] {str(title)[:60]}")
        else:
            error = r.get("error", "Error desconocido")
            title = r.get("title", r.get("titulo", ""))
            print(f"  [!!] {str(title)[:30]} -> {str(error)[:60]}")

    print()
    print("[3/3] Setup completado.")
    print("    Usa '/notebooklm' en el chat para acceder a tus cuadernos.")
    print("    Usa 'notebook_list_tagged #legal' para listar todos.")

    return results


if __name__ == "__main__":
    asyncio.run(setup_notebooks())
