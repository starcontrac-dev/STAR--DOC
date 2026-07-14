"""
Definiciones de Schemas de Herramientas para la API de Gemini.

Contiene TOOLS_SCHEMA, el arreglo que se envía a Gemini como
`function_declarations` para habilitar Function Calling.

También maneja la inyección dinámica de schemas de NotebookLM Legal
y la integración con el SkillManager.
"""

import logging

logger = logging.getLogger(__name__)

# --- DEFINICIONES DE SCHEMAS DE HERRAMIENTAS ---
TOOLS_SCHEMA = [
    {
        "function_declarations": [
            {
                "name": "list_templates",
                "description": "Lista todas las plantillas de documentos legales disponibles en el sistema. Usa esto cuando el usuario pregunte qué documentos puede crear.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                }
            },
            {
                "name": "get_template_variables",
                "description": "Obtiene las variables (campos a llenar) de una plantilla específica. Usa esto después de que el usuario elija una plantilla para saber qué preguntar.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING", "description": "El nombre exacto del archivo de la plantilla (ej: 'tutela.docx')."}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "generate_document",
                "description": "Genera el documento final cuando se tienen todas las variables llenas. Retorna la URL de descarga.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING", "description": "El nombre del archivo de la plantilla."},
                        "variables": {"type": "OBJECT", "description": "Objeto JSON con pares clave-valor para llenar la plantilla."}
                    },
                    "required": ["filename", "variables"]
                }
            },
            {
                "name": "validate_data",
                "description": "Valida los datos recolectados contra un esquema legal estricto antes de generar el documento. Retorna 'Datos Válidos' o una lista de errores que debes corregir preguntando al usuario.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "schema_name": {"type": "STRING", "description": "El nombre del esquema a validar (ej: 'TutelaSchema')."},
                        "data": {"type": "OBJECT", "description": "Objeto JSON con los datos a validar."}
                    },
                    "required": ["schema_name", "data"]
                }
            },
            {
                "name": "read_template_content",
                "description": "Lee el contenido completo de una plantilla (Word o Markdown) para analizar sus cláusulas y texto. Úsalo cuando el usuario pida analizar, resumir o comparar el contenido de una plantilla específica.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING", "description": "El nombre del archivo de la plantilla a leer (ej: 'contrato.docx')."}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "web_search",
                "description": "Busca información actualizada en internet usando Brave Search. Úsalo cuando el usuario pregunte sobre noticias recientes, leyes nuevas, jurisprudencia actual, precios de criptomonedas, o cualquier tema que requiera información en tiempo real. Retorna resultados con títulos, URLs y descripciones.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING", "description": "La consulta de búsqueda (ej: 'ley colombiana criptomonedas 2026', 'sentencia corte constitucional tutela')."},
                        "max_results": {"type": "INTEGER", "description": "Número máximo de resultados a retornar (default 5)."}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_my_documents",
                "description": "Lista los nombres e IDs de todos los documentos previamente subidos por el usuario a su Bóveda de Documentos RAG. Úsalo cuando el usuario haga referencia a un documento anterior o quiera comparar con documentos existentes en su cuenta.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {}
                }
            },
            {
                "name": "read_my_document",
                "description": "Lee el texto completo de un documento almacenado en la Bóveda RAG del usuario por su ID de documento. Se usa justo después de obtener la lista con list_my_documents.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "document_id": {"type": "INTEGER", "description": "El ID del documento a leer."}
                    },
                    "required": ["document_id"]
                }
            },
            {
                "name": "analizar_contrato",
                "description": "Analiza un contrato o documento legal completo con NLP (spaCy + regex jurídico colombiano). Extrae entidades (personas, organizaciones, fechas, dinero, normas), detecta cláusulas presentes/faltantes, identifica riesgos legales con fundamentación normativa y genera recomendaciones. Úsalo cuando el usuario pida analizar, auditar o revisar un contrato o documento legal.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "texto": {"type": "STRING", "description": "Texto completo del contrato o documento a analizar."},
                        "file_path": {"type": "STRING", "description": "Ruta al archivo del contrato (PDF, DOCX, TXT, MD). Alternativa a texto."}
                    }
                }
            },
            {
                "name": "extraer_entidades_documento",
                "description": "Extrae entidades nombradas (NER) de un texto legal: personas, organizaciones, fechas, montos, ubicaciones y referencias legales (leyes, decretos, sentencias). Úsalo cuando necesites identificar actores, fechas clave o normativa mencionada en un documento.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "texto": {"type": "STRING", "description": "Texto del documento a analizar."},
                        "max_entidades": {"type": "INTEGER", "description": "Máximo de entidades por categoría (default 50)."}
                    },
                    "required": ["texto"]
                }
            },
            {
                "name": "detectar_clausulas_documento",
                "description": "Detecta cláusulas contractuales presentes y faltantes en un contrato colombiano (objeto, salario, duración, terminación, confidencialidad, penalidades, jurisdicción, datos personales, etc.). Identifica riesgos legales con fundamentación normativa. Úsalo para auditoría rápida de contratos.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "texto": {"type": "STRING", "description": "Texto completo del contrato a evaluar."}
                    },
                    "required": ["texto"]
                }
            },
            {
                "name": "certificar_ipfs",
                "description": "Certifica un archivo local anclándolo en la blockchain/IPFS. Retorna el CID de IPFS, el hash SHA-256 de integridad y enlaces para visualizar el archivo y su certificado de evidencia HTML. Úsalo cuando el usuario pida certificar, guardar en blockchain, sellar o anclar en IPFS un archivo que acaba de generar o subir.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING", "description": "El nombre del archivo existente en la carpeta de salida (output) que se va a certificar (ej: 'Contrato_2026.docx')."},
                        "classification": {"type": "STRING", "description": "Nivel de seguridad: 'public', 'confidential' o 'chain_of_custody'. Por defecto es 'public'."}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "verificar_documento",
                "description": "Verifica criptográficamente un documento en IPFS utilizando su CID. Opcionalmente puede comparar el hash SHA-256 para comprobar si el documento ha sido modificado. Úsalo cuando el usuario quiera verificar la autenticidad o existencia de un documento sellado previamente.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "cid": {"type": "STRING", "description": "El Content Identifier (CID) de IPFS del documento a verificar."},
                        "sha256": {"type": "STRING", "description": "El hash SHA-256 original esperado para comprobar que no ha sido alterado (opcional)."}
                    },
                    "required": ["cid"]
                }
            },
            {
                "name": "empaquetar_auditoria",
                "description": "Agrupa múltiples documentos certificados en un único paquete o expediente digital en IPFS (Merkle DAG). Retorna el CID del directorio y los detalles del paquete. Úsalo cuando el usuario te pida agrupar, archivar, empaquetar o crear un expediente/auditoría con varios archivos.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "Nombre identificador de la auditoría (ej: 'Expediente_Tutela_Gomez')."},
                        "document_ids": {
                            "type": "ARRAY",
                            "items": {"type": "INTEGER"},
                            "description": "Lista de IDs numéricos de documentos a empaquetar."
                        }
                    },
                    "required": ["name", "document_ids"]
                }
            },
            {
                "name": "compare_documents",
                "description": "Compara dos textos de documentos legales para evaluar diferencias textuales y riesgos riesgos jurídicos bajo la ley colombiana. Úsala cuando el usuario te pida explícitamente comparar cláusulas, contratos o escritos.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "original_text": {"type": "STRING", "description": "Texto completo de la versión original (A)."},
                        "modified_text": {"type": "STRING", "description": "Texto completo de la versión modificada (B)."}
                    },
                    "required": ["original_text", "modified_text"]
                }
            },
            {
                "name": "buscar_normatividad_colombiana",
                "description": "Busca en la base de datos de conocimiento jurídico local la normatividad base colombiana (Constitución, Código Civil, Código de Comercio, Estatuto del Consumidor, CPACA) usando similitud semántica. Úsala cuando el usuario haga preguntas legales sobre la legislación colombiana.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING", "description": "La consulta jurídica a buscar (ej: 'requisitos de tutela', 'cláusulas abusivas consumidor', 'derecho de petición término')."},
                        "category": {"type": "STRING", "description": "Filtrar por categoría (opciones: 'constitucional', 'civil', 'comercial', 'consumidor', 'administrativo'). Opcional."},
                        "limit": {"type": "INTEGER", "description": "Límite de resultados a retornar (por defecto 3)."}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "guardar_norma_o_sentencia",
                "description": "Guarda, fragmenta e indexa una nueva norma, ley, artículo o sentencia judicial (jurisprudencia) en el almacén vectorial local pgvector para búsquedas futuras. Úsala cuando el usuario te pida explícitamente guardar, indexar o registrar una norma o sentencia en el RAG.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "source": {"type": "STRING", "description": "Nombre de la fuente (ej: 'Sentencia T-760/2008', 'Ley 2300 de 2023')."},
                        "citation": {"type": "STRING", "description": "Entidad emisora o cita de referencia (ej: 'Corte Constitucional', 'Congreso de la República'). Opcional."},
                        "content": {"type": "STRING", "description": "Texto completo o artículo legal a guardar en la base de datos."},
                        "category": {"type": "STRING", "description": "Categoría jurídica (opciones: 'constitucional', 'civil', 'comercial', 'consumidor', 'administrativo', 'tributario', 'crypto', 'jurisprudencia')."}
                    },
                    "required": ["source", "content", "category"]
                }
            }
            # Las herramientas de búsqueda web se envían en una llamada separada si es necesario
            # o se inyectan dinámicamente a través del SkillManager
        ]
    }
]

# --- INYECCIÓN DINÁMICA DE SCHEMAS DE EXPEDIENTES JUDICIALES ---
try:
    from app.core.skills.library.consulta_expedientes.tools import get_tools_schema as get_expedientes_schemas
    _expedientes_schemas = get_expedientes_schemas()
    _existing_names = {t["name"] for t in TOOLS_SCHEMA[0]["function_declarations"]}
    for es in _expedientes_schemas:
        if es["name"] not in _existing_names:
            TOOLS_SCHEMA[0]["function_declarations"].append(es)
            _existing_names.add(es["name"])
            logger.info(f"✅ Herramienta '{es['name']}' inyectada al schema global.")
except Exception as e:
    logger.warning(f"⚠️ No se pudo inyectar schema de expedientes: {e}")


def inject_notebook_schemas():
    """
    Inyecta permanentemente los schemas de NotebookLM Legal al schema global.
    Se ejecuta al importar este módulo.
    """
    try:
        from app.core.skills.library.notebooklm_legal.tools import get_tools_schema as get_notebook_schemas
        from app.core.skills.manager import SkillManager

        notebook_schemas = get_notebook_schemas()
        existing_tools = {t["name"] for t in TOOLS_SCHEMA[0]["function_declarations"]}
        added_count = 0
        for ns in notebook_schemas:
            # Sanitizamos igual que el skill_manager por si acaso
            sanitized = SkillManager._sanitize_gemini_schema(ns)
            if sanitized["name"] not in existing_tools:
                TOOLS_SCHEMA[0]["function_declarations"].append(sanitized)
                existing_tools.add(sanitized["name"])
                added_count += 1
        logger.info(f"✅ Inyectadas {added_count} herramientas de NotebookLM al schema global.")
    except Exception as e:
        logger.error(f"⚠️ Error inyectando schemas de NotebookLM globalmente: {e}")


# Ejecutar inyección al importar el módulo
inject_notebook_schemas()
