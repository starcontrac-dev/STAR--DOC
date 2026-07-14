import asyncio
import sys
import os

# Asegurar path de importación del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker
from app.services.rag_service import RAGService

async def main():
    print("=" * 80)
    # Título profesional que refleja el perfil técnico-legal de STAR-DOC
    print("🏛️  STAR-DOC: CONSULTOR DE CONOCIMIENTO JURÍDICO LOCAL (RAG JURÍDICO)  🏛️")
    print("=" * 80)
    print("Este buscador consulta tu base de datos local PostgreSQL con extensión pgvector.")
    print("Escribe tu duda jurídica colombiana o presiona Ctrl+C para salir.\n")
    
    while True:
        try:
            query = input("\n🔎 Escribe tu consulta jurídica: ").strip()
            if not query:
                continue
                
            print("Buscando en la base de datos local...")
            async with async_session_maker() as session:
                results = await RAGService.search_semantic(
                    session=session,
                    query=query,
                    limit=3,
                    threshold=0.45
                )
                
                if not results:
                    print("⚠️  No se encontraron fragmentos normativos con suficiente similitud (umbral > 0.45).")
                    continue
                    
                print(f"✨ Se encontraron {len(results)} fragmentos relevantes en la base de datos:\n")
                for idx, r in enumerate(results, 1):
                    # Formato claro y ordenado para lectura
                    print(f"📌 [{idx}] Similitud: {r['similarity'] * 100:.2f}% | Categoría: {r['category'].upper()}")
                    print(f"📖 Origen: {r['source']}")
                    print(f"🔖 Cita/Cuaderno: {r['citation']}")
                    print("-" * 50)
                    print(f"{r['content']}")
                    print("=" * 50)
                    
        except KeyboardInterrupt:
            print("\n\n👋 Saliendo del consultor interactivo. ¡Que tenga un excelente día!")
            break
        except Exception as e:
            print(f"❌ Ocurrió un error en la búsqueda: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
