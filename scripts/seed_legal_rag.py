import asyncio
import sys
import os

# Añadir raíz al path para importaciones
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_maker
from app.services.rag_service import RAGService
from sqlalchemy import text

# Datos semilla de normatividad base colombiana
LEGAL_CHUNKS = [
    {
        "source": "Constitución Política de Colombia",
        "citation": "Artículo 23",
        "category": "constitucional",
        "content": (
            "Toda persona tiene derecho a presentar peticiones respetuosas a las autoridades "
            "por motivos de interés general o particular y a obtener pronta resolución. "
            "El legislador podrá reglamentar su ejercicio ante organizaciones privadas para garantizar "
            "los derechos fundamentales."
        )
    },
    {
        "source": "Constitución Política de Colombia",
        "citation": "Artículo 86",
        "category": "constitucional",
        "content": (
            "Toda persona tendrá acción de tutela para reclamar ante los jueces, en todo momento y lugar, "
            "mediante un procedimiento preferente y sumario, por sí misma o por quien actúe a su nombre, "
            "la protección inmediata de sus derechos constitucionales fundamentales, cuando quiera que éstos "
            "resulten vulnerados o amenazados por la acción o la omisión de cualquier autoridad pública. "
            "La protección consistirá en una orden para que aquel respecto de quien se solicita la tutela, "
            "actúe o se abstenga de hacerlo. El fallo, que será de inmediato cumplimiento, podrá impugnarse "
            "ante el juez competente y, en todo caso, éste lo remitirá a la Corte Constitucional para su eventual revisión."
        )
    },
    {
        "source": "Constitución Política de Colombia",
        "citation": "Artículo 29",
        "category": "constitucional",
        "content": (
            "El debido proceso se aplicará a toda clase de actuaciones judiciales y administrativas. "
            "Nadie podrá ser juzgado sino conforme a leyes preexistentes al acto que se le imputa, "
            "ante juez o tribunal competente y con observancia de la plenitud de las formas propias de cada juicio. "
            "En materia penal, la ley permisiva o favorable, aun cuando sea posterior, se aplicará de preferencia "
            "a la restrictiva o desfavorable. Toda persona se presume inocente mientras no se la haya declarado "
            "judicialmente culpable."
        )
    },
    {
        "source": "Ley 1480 de 2011 (Estatuto del Consumidor)",
        "citation": "Artículo 42",
        "category": "consumidor",
        "content": (
            "Concepto y definición de Cláusulas Abusivas. Son cláusulas abusivas aquellas que producen un "
            "desequilibrio injustificado en perjuicio del consumidor y las que en las mismas condiciones "
            "afecten el tiempo, modo o lugar en que el consumidor puede ejercer sus derechos. Para establecer "
            "la naturaleza abusiva de una cláusula se tendrá en cuenta la naturaleza de los bienes o servicios "
            "objeto del contrato, todas las circunstancias que concurrieron al momento de su celebración y "
            "todas las demás cláusulas del contrato o de otro del cual este dependa."
        )
    },
    {
        "source": "Ley 1480 de 2011 (Estatuto del Consumidor)",
        "citation": "Artículo 43",
        "category": "consumidor",
        "content": (
            "Cláusulas abusivas ineficaces de pleno derecho. Son ineficaces de pleno derecho las cláusulas que: "
            "1. Limiten la responsabilidad del productor o proveedor de las obligaciones que por ley les corresponden; "
            "2. Impliquen la renuncia de los derechos del consumidor que por ley les corresponden; "
            "3. Inviertan la carga de la prueba en perjuicio del consumidor; "
            "4. Trasladen al consumidor o a un tercero que no sea parte del contrato la responsabilidad del productor o proveedor; "
            "5. Establezcan que el productor o proveedor pueda modificar unilateralmente el contrato o rescindirlo sin causa; "
            "6. Obliguen al consumidor a acudir a la justicia arbitral o a tribunales extranjeros."
        )
    },
    {
        "source": "Código de Comercio de Colombia",
        "citation": "Artículo 897",
        "category": "comercial",
        "content": (
            "Ineficacia de pleno derecho. Cuando en este Código se exprese que un acto no produce efectos, "
            "se entenderá que es ineficaz de pleno derecho, sin necesidad de declaración judicial. "
            "La ineficacia opera ipso jure y no requiere pronunciamiento o demanda judicial previa para surtir efectos."
        )
    },
    {
        "source": "Código de Comercio de Colombia",
        "citation": "Artículo 824",
        "category": "comercial",
        "content": (
            "Consensualidad en los contratos comerciales. Los comerciantes podrán expresar su voluntad "
            "de contratar u obligarse verbalmente, por escrito o por cualquier otro modo inequívoco. "
            "Cuando la ley exija una determinada solemnidad como requisito esencial del negocio jurídico, "
            "este no se formará sin dicha solemnidad."
        )
    },
    {
        "source": "Ley 1437 de 2011 (CPACA)",
        "citation": "Artículo 13",
        "category": "administrativo",
        "content": (
            "Objeto y modalidades del derecho de petición ante las autoridades. Toda persona tiene derecho "
            "a presentar peticiones respetuosas a las autoridades, en cualquiera de sus modalidades, verbalmente, "
            "por escrito o por cualquier otro medio idóneo y sin costo alguno. Las autoridades deberán garantizar "
            "la recepción y el trámite oportuno de las mismas. A través de este derecho se podrá solicitar el "
            "reconocimiento de un derecho, la intervención de una entidad, la resolución de una situación jurídica, "
            "la prestación de un servicio, requerir información, consultar examinar y requerir copias de documentos."
        )
    },
    {
        "source": "Ley 1437 de 2011 (CPACA)",
        "citation": "Artículo 14",
        "category": "administrativo",
        "content": (
            "Términos para resolver las distintas modalidades de peticiones. Salvo norma especial, toda petición "
            "deberá resolverse dentro de los quince (15) días siguientes a su recepción. "
            "Las peticiones de documentos y de información deberán resolverse dentro de los diez (10) días siguientes. "
            "Las peticiones de consulta ante las autoridades en relación con las materias a su cargo deberán "
            "resolverse dentro de los treinta (30) días siguientes a su recepción."
        )
    },
    {
        "source": "Código Civil de Colombia",
        "citation": "Artículo 1602",
        "category": "civil",
        "content": (
            "Fuerza vinculante de los contratos. Todo contrato legalmente celebrado es una ley para los contratantes, "
            "y no puede ser invalidado sino por su consentimiento mutuo o por causas legales. "
            "Los contratos deben ejecutarse de buena fe, y por consiguiente obligan no solo a lo que en ellos se expresa, "
            "sino a todas las cosas que emanan precisamente de la naturaleza de la obligación."
        )
    }
]

async def seed_rag():
    print("=== POBILANDO ALMACÉN VECTORIAL (RAG JURÍDICO COLOMBIANO) ===")
    async with async_session_maker() as session:
        # Limpiar registros previos para evitar duplicados
        await session.execute(text("TRUNCATE TABLE legal_knowledge_chunks RESTART IDENTITY;"))
        await session.commit()
        
        inserted = 0
        for chunk_data in LEGAL_CHUNKS:
            try:
                print(f"Indexando [{chunk_data['source']}] - {chunk_data['citation']}...")
                await RAGService.add_chunk(
                    session=session,
                    source=chunk_data["source"],
                    citation=chunk_data["citation"],
                    content=chunk_data["content"],
                    category=chunk_data["category"]
                )
                inserted += 1
            except Exception as e:
                print(f"Error indexando chunk: {e}")
                
        print(f"\n¡Semilla completada! Se indexaron {inserted} fragmentos normativos en pgvector.")

if __name__ == "__main__":
    asyncio.run(seed_rag())
