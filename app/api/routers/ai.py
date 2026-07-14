from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Depends, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from app.core.limiter import limiter
from typing import Optional, List, Dict, Any
import os
import logging
import json
import asyncio
import uuid
import time
import re
import copy
import datetime
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.schemas.common import GeminiRequest
from app.core.config import settings
from app.core.redis_client import redis_manager
from app.services.files import extract_text_from_bytes
from app.core.utils import sanitize_filename
from app.services.ai_service import ai_service
from app.core.skills.manager import SkillManager

# --- IMPORTS REFACTORIZADOS: Herramientas extraídas a app.api.tools ---
from app.api.tools import execute_tool, TOOLS_SCHEMA
from app.api.tools.registry import list_registered_tools

skill_manager = SkillManager()
logger = logging.getLogger(__name__)
router = APIRouter(tags=["Legal AI Engine"])
@router.get("/api/skills")
async def list_skills():
    """Lista todos los skills disponibles con metadata"""
    try:
        skills = skill_manager.list_available_skills()
        return {
            "skills": [
                {"id": skill_id, **metadata.model_dump()}
                for skill_id, metadata in skills.items()
            ]
        }
    except Exception as e:
        logger.error(f"Error list_skills: {e}")
        return {"skills": [], "error": str(e)}


@router.get("/api/templates-autocomplete")
async def templates_autocomplete(authorization: Optional[str] = Header(None)):
    """
    Endpoint ligero para autocompletado de menciones @ en el chat de IA.
    Retorna la lista de nombres de archivos de plantillas (.md, .docx)
    del directorio PLANTILLAS_DIR, excluyendo subdirectorios y archivos temporales.
    """
    # Validar autenticación básica
    if authorization and authorization.lower().startswith('bearer '):
        try:
            token = authorization.split(' ', 1)[1]
            jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except Exception:
            pass  # Permitir acceso sin auth para carga inicial ligera

    # Intentar leer desde Redis (DB 2)
    try:
        pool = await redis_manager.get_pool(db=2)
        cached = await pool.get("autocomplete:templates")
        if cached:
            return {"templates": json.loads(cached)}
    except Exception as ex:
        logger.warning(f"Error al leer caché de autocomplete de Redis: {ex}")
    
    try:
        plantillas_dir = settings.PLANTILLAS_DIR
        if not os.path.exists(plantillas_dir):
            return {"templates": []}
        
        # Listar solo archivos válidos (.md, .docx, .txt), excluyendo subdirectorios y temporales
        valid_extensions = {'.md', '.docx', '.txt'}
        templates = []
        for f in sorted(os.listdir(plantillas_dir)):
            full_path = os.path.join(plantillas_dir, f)
            if not os.path.isfile(full_path):
                continue
            # Excluir archivos temporales y backups
            if f.startswith('temp_') or f.startswith('.') or f.endswith('.bak'):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_extensions:
                templates.append(f)
        
        # Almacenar en Redis (DB 2) con un TTL de 120 segundos (2 minutos)
        try:
            pool = await redis_manager.get_pool(db=2)
            await pool.setex("autocomplete:templates", 120, json.dumps(templates))
        except Exception as ex:
            logger.warning(f"Error al guardar caché de autocomplete en Redis: {ex}")

        return {"templates": templates}
    except Exception as e:
        logger.error(f"Error listando plantillas para autocomplete: {e}")
        return {"templates": [], "error": str(e)}

@router.post("/api/gemini")
@limiter.limit("30/minute")
async def proxy_gemini(
    request: Request,
    gemini_request: GeminiRequest, 
    authorization: Optional[str] = Header(None)
):
    """
    Proxy endpoint con capacidades de AGENTE (Loop de Herramientas).
    """
    api_key = settings.GEMINI_API_KEY or (settings.GEMINI_API_KEYS[0] if settings.GEMINI_API_KEYS else None)
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured.")
    # Utilice gemini-2.5-flash para una mejor estabilidad y límites de nivel gratuitos más altos
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}" 
    
    # --- AUTH ---
    username = "Anonimo"
    if authorization and authorization.lower().startswith('bearer '):
        try:
            token = authorization.split(' ', 1)[1]
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get('sub', "Anonimo")
        except: pass

    # --- INITIAL CONTEXT ---
    contents = []
    
    # System Instruction
    import datetime
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # --- RAG CONTEXT (pgvector) ---
    rag_context = ""
    try:
        from app.database import async_session_maker
        from app.services.rag_service import RAGService
        
        # Ejecutamos la búsqueda vectorial semántica de forma asíncrona abriendo una sesión ligera
        async with async_session_maker() as db_session:
            # Buscamos similitud coseno >= 0.65 (umbral balanceado) y limitamos a 3 fragmentos
            rag_results = await RAGService.search_semantic(
                session=db_session,
                query=gemini_request.prompt,
                threshold=0.65,
                limit=3
            )
            
            if rag_results:
                logger.info(f"RAG pgvector: Encontrados {len(rag_results)} fragmentos legales relevantes.")
                formatted_chunks = []
                for idx, r in enumerate(rag_results, 1):
                    formatted_chunks.append(
                        f"Fragmento {idx}:\n"
                        f"- Fuente: {r['source']}\n"
                        f"- Cita: {r['citation']}\n"
                        f"- Categoría: {r['category']}\n"
                        f"- Contenido: {r['content']}\n"
                        f"- Similitud Coseno: {r['similarity']:.4f}\n"
                    )
                rag_context = "\n".join(formatted_chunks)
    except Exception as ex_rag:
        logger.error(f"Error al recuperar contexto RAG de pgvector: {ex_rag}")

    sys_instruction = gemini_request.system_instruction or "Eres un asistente útil."
    
    if gemini_request.skill_id:
        sys_instruction = skill_manager.get_system_prompt_with_skills(sys_instruction, gemini_request.skill_id)

    sys_instruction += f"\n\nFECHA ACTUAL: {current_date}"
    sys_instruction += "\nERES UN CONSULTOR SENIOR, EXPERTO ABOGADO ESPECIALIZADO EN DERECHO COLOMBIANO."
    sys_instruction += "\nTu objetivo es ayudar al usuario a redactar documentos y resolver dudas con PROFUNDIDAD EXTREMA."
    sys_instruction += "\n0. REGLA DE ESTILO CRÍTICA: Tus respuestas deben ser MUY VERBOSAS, detalladas, proactivas, largas, estructuradas y fundamentadas legalmente. Explica bien, con precisión legal. No escatimes en descripciones."
    sys_instruction += "\n1. Si el usuario pide un documento o borrador, SIEMPRE ENTREGA EL BORRADOR COMPLETO en formato Markdown directamente en el chat."
    sys_instruction += "\n2. REGLA DE VARIABLES CRÍTICA: En cualquier borrador o plantilla que generes, TODOS los datos a llenar DEBEN ir encerrados exactamente en DOBLE CORCHETE con guiones bajos (formato Python variable). Ejemplo: {{nombre_completo}}, {{fecha_contrato}}, {{salario_mensual}}. NUNCA uses [nombre] ni otra sintaxis."
    sys_instruction += "\n3. Si el usuario pide generar el documento en archivo, usa `list_templates` para ver qué hay o usa las plantillas adjuntas vía @."
    sys_instruction += "\n4. Si el usuario pregunta sobre el CONTENIDO de una plantilla, USA `read_template_content`."
    sys_instruction += "\n5. Usa `get_template_variables` para saber qué preguntar al llenar una plantilla."
    sys_instruction += "\n6. Entrevista al usuario amablemente, obteniendo los datos requeridos."
    sys_instruction += "\n4. Cuando tengas TODO, usa `generate_document`."
    sys_instruction += "\n5. Si el usuario pregunta sobre hechos recientes, leyes nuevas, noticias, jurisprudencia actual o precios, USA `web_search` para obtener información actualizada de internet."
    sys_instruction += "\n6. IMPORTANTE: Al responder sobre noticias o leyes, verifica la fecha del resultado de búsqueda. Si la noticia es de 2025 o 2026, ES PROBABLEMENTE ACTUAL dependiendo de la fecha de hoy."
    sys_instruction += "\n7. Responde siempre en español y formateado en Markdown."
    sys_instruction += "\n8. Si el usuario sube un archivo y dice 'usa esto como plantilla', USA el nombre del archivo adjunto (ej: 'temp_xyz.docx') en `get_template_variables`."
    sys_instruction += "\n9. IMPORTANTE: Antes de `generate_document` para una Tutela, DEBES llamar a `validate_data` con schema_name='TutelaSchema'. Si hay errores, pide al usuario que los corrija."
    sys_instruction += "\n10. Si ves '--- PLANTILLA ADJUNTA ---' en el contexto (traída por comando @), y el usuario quiere 'llenar', 'generar' o 'crear' el documento:\n    a) NO te limites a escribir el texto en el chat.\n    b) DEBES usar la herramienta `generate_document`.\n    c) Extrae las variables del contexto o pídelas si faltan."
    sys_instruction += "\n11. REGLA CRÍTICA DE ENLACES: Cuando la herramienta `generate_document` retorna éxito, su respuesta será un JSON con estos campos:\n    - filename: el nombre REAL del archivo (ej: 'BIENVENIDA_20260403_143022.docx')\n    - download_url: la URL REAL de descarga (ej: '/files/BIENVENIDA_20260403_143022.docx')\n    DEBES usar EXACTAMENTE ese download_url en tu respuesta al usuario."
    sys_instruction += "\n12. PROHIBIDO INVENTAR ENLACES: JAMÁS escribas enlaces como '/generar_documento/...' o '/descargar/...'. SÓLO están permitidos los enlaces que empiezan por '/files/' y cuyo nombre de archivo fue DEVUELTO POR LA HERRAMIENTA `generate_document`."
    sys_instruction += "\n    MALO: [Descargar](/generar_documento?id=123) -> ESTO DA ERROR 404."
    sys_instruction += "\n    MALO: [Descargar](/files/Contrato_Final.docx) -> INVENTASTE EL NOMBRE, ERROR 404."
    sys_instruction += "\n    BUENO: [Descargar Documento](/files/BIENVENIDA_20260403_143022.docx) -> USASTE EL NOMBRE QUE DEVOLVIÓ LA HERRAMIENTA."
    sys_instruction += "\n13. MANEJO DE ERRORES: Si la herramienta `generate_document` devuelve un ERROR (ej: {'error': '...'}), DEBES DECIRLE AL USUARIO EL ERROR EXACTO. NO inventes que salió bien. NO inventes un enlace."
    sys_instruction += "\n14. Si la conversión del documento falla, la herramienta puede devolver un archivo .md o .txt en lugar de .docx. En ese caso, entrega ese enlace y explica que no se pudo convertir a Word."
    sys_instruction += "\n16. La herramienta `web_search` retorna resultados con título, URL y descripción. Úsalos para responder preguntas sobre actualidad, leyes nuevas, jurisprudencia reciente, o cualquier tema que requiera información fresca. Cita las fuentes cuando sea posible."
    sys_instruction += "\n17. AHORA TIENES UNA BÓVEDA RAG. Si el usuario te dice 'lee el documento que subí ayer', utiliza inmediatamente la herramienta `list_my_documents` e inspecciona los IDs. Luego usa `read_my_document` pasándole el ID que corresponda."
    sys_instruction += "\n18. SUGERENCIAS INTELIGENTES: Al final de tu respuesta final (cuando ya no necesites usar más herramientas), DEBES añadir un bloque con 2 sugerencias de preguntas cortas y útiles que el usuario podría hacer a continuación. Usa exactamente este formato al final de todo: |||Suggestions: [\"Pregunta 1\", \"Pregunta 2\"]|||"
    # --- INSTRUCCIONES NOTEBOOKLM v2.0 ---
    sys_instruction += "\n19. TIENES BASE DE CONOCIMIENTO JURÍDICO (NotebookLM v2.0): Cuando el usuario pregunte sobre leyes, sentencias, jurisprudencia o doctrina colombiana, PRIORIZA `notebook_query_legal` sobre `web_search`. Las respuestas de NotebookLM son fundamentadas con CERO alucinaciones y CITAS VERIFICABLES."
    sys_instruction += "\n20. ETIQUETADO CRÍTICO: Los cuadernos se dividen en dos categorías principales:"
    sys_instruction += "\n    - LEGISLACIÓN (#legal): Usa etiquetas como #legal-constitucional, #legal-civil, #legal-comercial, #legal-tributario, #legal-laboral, #legal-crypto."
    sys_instruction += "\n    - JURISPRUDENCIA (#juris): Usa etiquetas como #juris-corte_constitucional, #juris-consejo_estado, #juris-corte_suprema."
    sys_instruction += "\n21. HERRAMIENTAS CLAVE:"
    sys_instruction += "\n    - `notebook_list_tagged`: Úsala SIEMPRE para ver qué cuadernos existen. Pasa la etiqueta completa (ej: '#juris')."
    sys_instruction += "\n    - `notebook_query_legal`: Úsala para preguntar. Pasa category='legal' o category='juris' según lo que el usuario pida."
    sys_instruction += "\n    - `notebook_create_legal`: Usa el parámetro `titulo` (no name). Etiqueta siempre con el área correcta."
    sys_instruction += "\n    - `notebook_status`: Verifica el estado general (usa check_connectivity=True para health check)."
    sys_instruction += "\n22. Si el usuario pregunta algo general, intenta buscar en ambas categorías o pregunta si prefiere ver la ley o la jurisprudencia reciente."
    sys_instruction += "\n22. REGLA DE INTERFAZ DE AUDITORÍA: Si utilizas la herramienta `analizar_contrato`, una vez recibas el JSON de la herramienta, DEBES incluirlo íntegramente al final de tu respuesta (oculto para el usuario pero legible para la UI) usando este formato exacto: |||LegalAnalysis: {el_json_de_la_herramienta} |||. IMPORTANTE: El JSON debe ser estrictamente válido, asegurándote de usar `true` y `false` en minúsculas (formato JSON estándar, NO formato Python)."
    sys_instruction += "\n23. CONSULTA DE EXPEDIENTES JUDICIALES: Cuando el usuario pregunte por el estado de un proceso judicial, un radicado, o quiera consultar un expediente, usa `buscar_expediente_judicial`. Si no proporciona un número de radicación, pídelo. Soporta búsqueda por radicación (ej: 11001-31-03-027-2024-00123-00), nombre de parte, o sentencia de la Corte Constitucional (ej: T-760/2008). Para procesos del Consejo de Estado, usa portal='samai'."
    sys_instruction += "\n24. INGESTA AUTOMATIZADA DE JURISPRUDENCIA: Cuando el usuario te pida ingestar, indexar o buscar y agregar sentencias (ej. 'busca e ingesta la sentencia T-760 de 2008' o 'agrega jurisprudencia sobre prepensionados'), USA `notebook_ingest_jurisprudencia`. Esta herramienta busca de forma automática en portales oficiales colombianos (.gov.co), prioriza las mejores fuentes y las añade al cuaderno."
    sys_instruction += "\n25. CONSTRUCTOR DE LÍNEAS JURISPRUDENCIALES: Cuando el usuario te pida analizar la jurisprudencia o construir una línea jurisprudencial de un tema o problema jurídico (ej. 'haz una línea jurisprudencial sobre estabilidad laboral reforzada'), USA `notebook_linea_jurisprudencial`. Analizará las fuentes de jurisprudencia y estructurará el análisis identificando sentencia hito, confirmatorias, modificatorias, ratio decidendi y estado actual."
    sys_instruction += "\n26. AUDITORÍA ADVERSARIAL (RED TEAM JUDICIAL): Si el usuario te pide auditar, criticar, evaluar o encontrar fallas en un escrito jurídico, contrato o memorial (ej. '/red-team' o 'analiza los vacíos de este escrito'), USA `notebook_red_team_legal`. Realizará una validación de vigencia de las citas normativas, detectará debilidades y vacíos argumentativos simulando la defensa de la contraparte."
    sys_instruction += "\n27. COMPARACIÓN DE DOCUMENTOS (DIFF IA): Si el usuario te pide comparar dos textos, cláusulas o contratos, USA la herramienta `compare_documents` pasándole los dos textos correspondientes. Una vez recibidos el diff y la evaluación de riesgos, resume de forma clara los cambios y riesgos principales, e indica al usuario que puede hacer clic en el botón de la cabecera (Comparar Documentos) para abrir la interfaz gráfica y revisar las líneas añadidas o eliminadas y el informe legal estructurado."
    
    # Inyectar el contexto RAG recuperado si existe
    if rag_context:
        sys_instruction += "\n\nCONTEXTO JURÍDICO OFICIAL RECUPERADO DE LA BÓVEDA DE JURISPRUDENCIA (pgvector):"
        sys_instruction += "\nResponde al usuario basándote prioritariamente en el siguiente contexto jurídico oficial de la legislación y jurisprudencia colombiana. Si el contexto es pertinente, cítalo explícitamente (ej: 'según el Artículo X de la Ley Y...'):"
        sys_instruction += "\n---"
        sys_instruction += f"\n{rag_context}"
        sys_instruction += "\n---"
        sys_instruction += "\nREGLAS DE CONTEXTO RAG:"
        sys_instruction += "\n1. Cita siempre la fuente oficial exacta (artículo, código, ley o número de sentencia de la Corte/Consejo) proporcionada en el contexto."
        sys_instruction += "\n2. Si la consulta del usuario no se puede responder directamente con el contexto jurídico recuperado, responde usando tus conocimientos legales generales colombianos fundamentándolos debidamente y sin alucinar."

    # Regla de Oro para la interfaz
    suggestion_rule = "\n\nREGLA OBLIGATORIA DE INTERFAZ: Al terminar tu respuesta literal (sin más herramientas), DEBES añadir 2 sugerencias de seguimiento en este formato exacto: |||Suggestions: [\"Pregunta 1\", \"Pregunta 2\"]|||. ESTO ES VITAL PARA LA UI.\n"
    
    contents.append({"role": "user", "parts": [{"text": sys_instruction + suggestion_rule}]})
    contents.append({"role": "model", "parts": [{"text": f"Entendido, soy tu asistente STAR-DOC. Hoy es {current_date}. Seguiré todas tus reglas, incluida la de añadir sugerencias contextuales al final de mis respuestas. ¿En qué puedo ayudarte?"}]})

    # Document Context
    if gemini_request.document_context:
        contents.append({"role": "user", "parts": [{"text": f"CONTEXTO ADICIONAL:\n{gemini_request.document_context}"}]})
        contents.append({"role": "model", "parts": [{"text": "Entendido."}]})
    
    # Web Search Context (Pre-fetch manual removed in favor of Native Tool)
    # El usuario solicitó explícitamente usar "tools de gemini para buscar en internet"
    
    # History
    if gemini_request.history:
        for item in gemini_request.history:
             if 'role' in item and 'parts' in item:
                contents.append({"role": item["role"], "parts": item["parts"]})

    # Current User Prompt
    import re
    
    # --- @ MENTION HANDLING ---
    # Buscar menciones tipo @NombrePlantilla
    # Admitimos letras, números, guiones, puntos y espacios (si se usan comillas, pero por ahora simple)
    mentions = re.findall(r'@([\w\-\.]+)', gemini_request.prompt)
    
    mentioned_context = ""
    if mentions:
        logger.info(f"Menciones de plantilla detectadas: {mentions}")
        for mention in mentions:
            # Buscar coincidencia aproximada o exacta
            target_file = None
            
            # 1. Búsqueda exacta
            p1 = os.path.join(settings.PLANTILLAS_DIR, mention)
            if os.path.exists(p1) and os.path.isfile(p1): target_file = p1
            
            # 2. Búsqueda con extensiones
            if not target_file:
                for ext in ['.md', '.docx', '.txt']:
                    p2 = os.path.join(settings.PLANTILLAS_DIR, f"{mention}{ext}")
                    if os.path.exists(p2) and os.path.isfile(p2):
                        target_file = p2
                        break
            
            # 3. Búsqueda parcial (si el usuario dice @Bienvenida y el archivo es BIENVENIDA.md)
            if not target_file:
                try:
                    all_files = os.listdir(settings.PLANTILLAS_DIR)
                    for f in all_files:
                        if mention.lower() in f.lower():
                            target_file = os.path.join(settings.PLANTILLAS_DIR, f)
                            break
                except: pass

            if target_file:
                try:
                    fname = os.path.basename(target_file)
                    with open(target_file, "rb") as f: blob = f.read()
                    text = await extract_text_from_bytes(blob, fname)
                    # Truncate if huge
                    if len(text) > 100000: text = text[:100000] + "\n...[TRUNCADO]"
                    
                    mentioned_context += f"\n\n--- PLANTILLA ADJUNTA: {fname} ---\n{text}\n---------------------------------\n"
                except Exception as e:
                    logger.error(f"Error leyendo plantilla mencionada {mention}: {e}")

    if mentioned_context:
        contents.append({"role": "user", "parts": [{"text": f"SYSTEM: El usuario ha mencionado plantillas existentes. Se adjunta su contenido para que LO USES como base:\n{mentioned_context}"}]})
        contents.append({"role": "model", "parts": [{"text": "Entendido. Usaré el contenido de estas plantillas adjuntas para responder."}]})

    # User Prompt con refuerzo de sugerencias
    suggestion_reminder = "\n\nIMPORTANTE PARA LA INTERFAZ: Finaliza tu respuesta final SIEMPRE con exactamente 2 sugerencias en el formato: |||Suggestions: [\"P1\", \"P2\"]|||."
    contents.append({"role": "user", "parts": [{"text": gemini_request.prompt + suggestion_reminder}]})

    # --- DECISIÓN DE HERRAMIENTAS ---
    use_web_search = gemini_request.web_search
    
    if use_web_search:
        logger.info("Modo búsqueda web activado (solo google_search)")
        tools = [{"google_search": {}}]
        payload = {"contents": contents, "tools": tools}
    else:
        logger.info("Modo agente activado (herramientas personalizadas)")
        import copy
        tools = copy.deepcopy(TOOLS_SCHEMA)
        
        if gemini_request.skill_id:
            skill_tools = skill_manager.get_skill_tools(gemini_request.skill_id)
            if skill_tools and skill_tools.get("schema"):
                if tools and "function_declarations" in tools[0]:
                    existing_names = {t["name"] for t in tools[0]["function_declarations"]}
                    for new_tool in skill_tools.get("schema", []):
                        if new_tool["name"] not in existing_names:
                            tools[0]["function_declarations"].append(new_tool)
                            existing_names.add(new_tool["name"])
                            
        # Final safety deduplication
        if tools and "function_declarations" in tools[0]:
            unique_tools = []
            seen_names = set()
            for t in tools[0]["function_declarations"]:
                if t["name"] not in seen_names:
                    seen_names.add(t["name"])
                    unique_tools.append(t)
            tools[0]["function_declarations"] = unique_tools

        payload = {"contents": contents, "tools": tools}

    if gemini_request.stream:
        async def agent_event_generator():
            from app.database import async_session_maker
            async with async_session_maker() as session:
                try:
                    if use_web_search:
                        yield f"data: {json.dumps({'type': 'status', 'msg': 'Iniciando búsqueda web...'})}\n\n"
                        # Usamos el streaming directo del modelo (cascada habilitada)
                        async for chunk in ai_service.stream_generate_content(payload=payload):
                            yield f"data: {json.dumps(chunk)}\n\n"
                            await asyncio.sleep(0.01)
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return

                    # MODO AGENTE CON STREAMING DE STATUS Y FALLBACK A TEXTO
                    MAX_TURNS = 10
                    current_turn = 0
                    yield f"data: {json.dumps({'type': 'status', 'msg': 'Iniciando agente...'})}\n\n"

                    while current_turn < MAX_TURNS:
                        current_turn += 1
                        
                        # Llamada a Gemini en el loop (sincrónica internamente porque predecir function_call_chunks es inestable)
                        response_data = await ai_service.generate_content(
                            payload=payload,
                            timeout=45.0,
                            add_grounding=False
                        )

                        candidates = response_data.get("candidates", [])
                        if not candidates:
                            yield f"data: {json.dumps({'type': 'error', 'msg': 'Sin respuesta'})}\n\n"
                            return

                        candidate = candidates[0]
                        content_parts = candidate.get("content", {}).get("parts", [])

                        has_function_calls = False
                        for part in content_parts:
                            if "functionCall" in part:
                                has_function_calls = True
                                break

                        if not has_function_calls:
                            # Hemos terminado las herramientas, enviamos el texto de vuelta en chunks simulados
                            text_response = " ".join([p.get("text", "") for p in content_parts if "text" in p])
                            
                            # Extraer sugerencias inteligentes
                            suggestions = []
                            suggestion_match = re.search(r"\|\|\|Suggestions:\s*(\[.*?\])\s*\|\|\|", text_response, re.DOTALL)
                            if suggestion_match:
                                logger.info(f"✨ Sugerencias encontradas en la respuesta: {suggestion_match.group(1)}")
                                try:
                                    suggestions_json = suggestion_match.group(1)
                                    suggestions = json.loads(suggestions_json)
                                    text_response = text_response.replace(suggestion_match.group(0), "").strip()
                                except Exception as e:
                                    logger.error(f"Error parseando sugerencias: {e}")
                            else:
                                logger.warning("⚠️ No se encontraron sugerencias en la respuesta final de la IA.")
                                logger.debug(f"Respuesta cruda: {text_response}")

                            # Simular streaming de texto suave
                            chunk_size = 30
                            for i in range(0, len(text_response), chunk_size):
                                yield f"data: {json.dumps({'type': 'chunk', 'text': text_response[i:i+chunk_size]})}\n\n"
                                await asyncio.sleep(0.02)
                            
                            # Enviar sugerencias si existen
                            if suggestions:
                                yield f"data: {json.dumps({'type': 'suggestions', 'data': suggestions})}\n\n"
                                
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            return
                        
                        # Ejecutar tools e informar al frontend
                        tool_results = []
                        for part in content_parts:
                            if "functionCall" in part:
                                func_call = part["functionCall"]
                                func_name = func_call.get("name")
                                func_args = func_call.get("args", {})
                                
                                yield f"data: {json.dumps({'type': 'status', 'msg': f'Ejecutando {func_name}...'})}\n\n"
                                
                                try:
                                    task = asyncio.create_task(execute_tool(func_name, func_args, session, username))
                                    # Loop de keep-alive para evitar ERR_INCOMPLETE_CHUNKED_ENCODING
                                    while not task.done():
                                        done, pending = await asyncio.wait([task], timeout=5.0)
                                        if not done:
                                            yield f"data: {json.dumps({'type': 'status', 'msg': f'Analizando base jurídica ({func_name})...'})}\n\n"
                                    result = task.result()
                                except Exception as e:
                                    result = {"error": str(e)}

                                tool_results.append({
                                    "functionResponse": {
                                        "name": func_name,
                                        "response": {
                                            "name": func_name,
                                            "content": result
                                        }
                                    }
                                })

                        payload["contents"].append({"role": "model", "parts": content_parts})
                        payload["contents"].append({"role": "user", "parts": tool_results})
                        
                    yield f"data: {json.dumps({'type': 'error', 'msg': 'Máximo de iteraciones alcanzado'})}\n\n"

                except Exception as e:
                    logger.error(f"Error en stream response: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"

        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
        return StreamingResponse(agent_event_generator(), media_type="text/event-stream", headers=headers)

    # --- FALLBACK: NO-STREAM RESPONSE ---
    from app.database import async_session_maker
    async with async_session_maker() as session:
        if use_web_search:
            try:
                response_data = await ai_service.generate_content(
                    payload=payload,
                    timeout=60.0,
                    add_grounding=True
                )
                return JSONResponse(content=response_data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        logger.info("Iniciando agent loop con herramientas personalizadas")
        MAX_TURNS = 10

        try:
            # Asegurar que la regla de sugerencias esté al final del último mensaje del usuario
            if payload["contents"] and payload["contents"][-1]["role"] == "user":
                payload["contents"][-1]["parts"][0]["text"] += "\n\nIMPORTANTE: Recuerda terminar tu respuesta final con las 3 sugerencias en el formato |||Suggestions: [...]|||."
            
            # --- MODEL CALL ---
            current_turn = 0
            while current_turn < MAX_TURNS:
                current_turn += 1
                logger.info(f"Agent turn {current_turn}/{MAX_TURNS}")

                # Usar ai_service con cascada de modelos
                # NOTA: NO usamos add_grounding aquí porque el modo agente usa Function Calling
                # y Gemini no permite combinar google_search con function_declarations
                response_data = await ai_service.generate_content(
                    payload=payload,
                    timeout=120.0,
                    add_grounding=False  # Desactivado para modo agente (conflicto con FC)
                )

                # Verificar si hay tool calls en la respuesta
                candidates = response_data.get("candidates", [])
                if not candidates:
                    logger.warning("No candidates in Gemini response")
                    return JSONResponse(content=response_data)

                candidate = candidates[0]
                content_parts = candidate.get("content", {}).get("parts", [])

                # Buscar function_calls en las partes
                has_function_calls = False
                for part in content_parts:
                    if "functionCall" in part:
                        has_function_calls = True
                        break

                if not has_function_calls:
                    # No hay más tool calls, devolver respuesta final
                    logger.info(f"Agent completed after {current_turn} turns")
                    return JSONResponse(content=response_data)

                # Ejecutar las herramientas solicitadas
                tool_results = []
                for part in content_parts:
                    if "functionCall" in part:
                        func_call = part["functionCall"]
                        func_name = func_call.get("name")
                        func_args = func_call.get("args", {})

                        logger.info(f"Executing tool: {func_name} with args: {func_args}")

                        try:
                            result = await execute_tool(func_name, func_args, session, username)
                            logger.info(f"Tool {func_name} result: {str(result)[:200]}")
                        except Exception as e:
                            logger.error(f"Tool {func_name} error: {e}")
                            result = {"error": f"Error ejecutando {func_name}: {str(e)}"}

                        tool_results.append({
                            "functionResponse": {
                                "name": func_name,
                                "response": {
                                    "name": func_name,
                                    "content": result
                                }
                            }
                        })

                # Añadir tool results al payload para la siguiente iteración
                payload["contents"].append({
                    "role": "model",
                    "parts": content_parts
                })
                payload["contents"].append({
                    "role": "user",
                    "parts": tool_results
                })

                logger.info(f"Tool results added, continuing agent loop")

            # Si llegamos aquí, se excedió el máximo de turns
            logger.warning(f"Agent loop exceeded {MAX_TURNS} turns, returning last response")
            return JSONResponse(content=response_data)

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"Gemini Request Error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FASE 1.3: ENDPOINTS DE MÉTRICAS Y HEALTH CHECK
# ============================================================================

@router.get("/api/ai/metrics")
async def get_ai_metrics():
    """
    Endpoint de métricas avanzadas de IA (FASE 1.3).
    Retorna estadísticas de uso, latencia, costos y estado de circuit breakers.
    """
    return ai_service.get_detailed_metrics()


@router.post("/api/ai/health-check")
async def run_health_check():
    """
    Endpoint para ejecutar health check manual de todos los modelos (FASE 3.3).
    Retorna el estado de salud de cada modelo.
    """
    try:
        health_status = await ai_service.run_health_check_now()
        return {
            "status": "success",
            "health": health_status,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/api/ai/status")
async def get_ai_status():
    """
    Endpoint ligero de estado de los modelos (sin ejecutar health check).
    """
    return {
        "models": ai_service.models,
        "active_api_keys": len(ai_service.api_keys),
        "circuit_breakers": {
            model: cb.state.value
            for model, cb in ai_service.circuit_breakers.items()
        },
        "quick_stats": {
            model: {
                "total": stats["total"],
                "success_rate": round((stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0, 2),
                "avg_latency_ms": round((stats["total_latency_ms"] / stats["total"]) if stats["total"] > 0 else 0, 2),
            }
            for model, stats in ai_service.model_stats.items()
        }
    }


@router.post("/api/extract-text")
async def extract_text_endpoint(file: UploadFile = File(...)):
    from app.services.files import extract_text_from_bytes
    if not file: raise HTTPException(400, "No file")
    
    # 1. Read content
    content = await file.read()
    
    # 2. Save to temp folder (for docxtpl usage)
    temp_dir = os.path.join(settings.PLANTILLAS_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    safe_name = sanitize_filename(file.filename)
    # Add UUID to avoid collisions
    saved_filename = f"temp_{uuid.uuid4().hex[:8]}_{safe_name}"
    saved_path = os.path.join(temp_dir, saved_filename)
    
    with open(saved_path, "wb") as f:
        f.write(content)
        
    # 3. Extract text
    text = await extract_text_from_bytes(content, file.filename)
    
    return {"text": text, "filename": saved_filename}


# ============================================================================
# FASE 4: SECRETARIO VIRTUAL (SALES ASSISTANT)
# ============================================================================

@router.post("/api/ai/sales-assistant", response_class=HTMLResponse)
@limiter.limit("20/minute")
async def ai_sales_assistant(
    request: Request,
    message: str = Form(...),
    history: str = Form("[]"),
    db: AsyncSession = Depends(get_session)
):
    """
    Endpoint de Secretario Virtual con capacidad de usar herramientas (Function Calling)
    para capturar leads y agendar reuniones.
    """
    from app.ai.prompts import SECRETARY_SYSTEM_PROMPT
    from app.ai.tools_schema import gemini_secretary_tools
    from app.services.secretary_service import SecretaryService
    import uuid

    try:
        history_list = json.loads(history)
    except:
        history_list = []
        
    session_id = uuid.uuid4().hex
        
    contents = []
    contents.append({"role": "user", "parts": [{"text": SECRETARY_SYSTEM_PROMPT}]})
    contents.append({"role": "model", "parts": [{"text": "Entendido. Soy LUKA, asistente virtual de Star-Doc. Conozco todas las funcionalidades de la plataforma (automatización de documentos, jurisprudencia, auditoría de contratos, IA legal). Responderé preguntas informativas con entusiasmo, orientaré sobre temas legales generales, y cuando detecte interés genuino en contratar o agendar una demo, usaré las herramientas de captura de leads y agendamiento. Siempre finalizaré con sugerencias relevantes."}]})
    
    # Inyectar historial local
    for item in history_list:
        if 'role' in item and 'parts' in item:
            contents.append({"role": item["role"], "parts": item["parts"]})
            
    # Añadir mensaje actual
    contents.append({"role": "user", "parts": [{"text": message}]})
    
    MAX_ITERATIONS = 3
    tool_executed = False
    
    for iteration in range(MAX_ITERATIONS):
        # Asegurarnos de que el payload incita al formato de suggestions
        if contents[-1]["role"] == "user" and not tool_executed:
            contents[-1]["parts"][0]["text"] += "\n\nIMPORTANTE: Finaliza tu respuesta final SIEMPRE con las 3 sugerencias inteligentes en el formato |||Suggestions: [...]|||."
            
        payload = {
            "contents": contents,
            "tools": [gemini_secretary_tools]
        }
        
        response_data = await ai_service.generate_content(
            payload=payload,
            timeout=25.0,
            add_grounding=False 
        )
        
        candidates = response_data.get("candidates", [])
        if not candidates:
            bot_reply = "Entiendo. ¿En qué más puedo ayudarte con la automatización legal?"
            break
            
        content_part = candidates[0].get("content", {})
        parts = content_part.get("parts", [])
        
        # Guardar en caso de que necesitemos devolverlo tal cual
        contents.append({"role": "model", "parts": parts})
        
        # Verificar si hay llamadas a función
        function_calls = [p.get("functionCall") for p in parts if "functionCall" in p]
        
        if not function_calls:
            # Respuesta final obtenida (sin functionCalls)
            bot_reply = "".join([p.get("text", "") for p in parts if "text" in p])
            break
            
        # Ejecutar todas las funciones (idealmente una por vez, pero soportamos array por si acaso)
        responses_parts = []
        for call in function_calls:
            tool_name = call.get("name")
            args = call.get("args", {})
            try:
                tool_result = await SecretaryService.execute_tool(tool_name, args, db, session_id)
            except Exception as e:
                logger.error(f"Error ejecutando tool {tool_name}: {e}")
                tool_result = {"error": str(e)}
                
            responses_parts.append({
                "functionResponse": {
                    "name": tool_name,
                    "response": tool_result
                }
            })
            
        contents.append({"role": "user", "parts": responses_parts})
        tool_executed = True
        # En la siguiente iteración el modelo responderá tomando en cuenta los resultados
    
    else:
        # Qué hacer si excede iteraciones (fallback)
        bot_reply = "Hubo un pequeño retraso, ¿puedes repetirme la solicitud por favor?"
        
    import re
    # Convertir negritas e itálicas de Markdown a HTML
    # Corregido: Usar patrones literales para las estrellas de markdown
    html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', bot_reply)
    html_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_content)
    # Reemplazar saltos de línea reales por <br> para el HTML
    html_content = html_content.replace('\n', '<br>')
    
    # Limpiar etiquetas HTML para el TTS (voz)
    # También remover el bloque de sugerencias del TTS para que no las lea en voz alta
    bot_reply_clean = re.sub(r'\|\|\|Suggestions:.*?\|\|\|', '', html_content, flags=re.DOTALL)
    bot_reply_clean = re.sub(r'<[^>]+>', '', bot_reply_clean)
    # Escapar comillas invertidas para el JS y remover saltos de línea para el string JS
    bot_reply_escaped_js = bot_reply_clean.replace('`', '\\`').replace('\n', ' ')
    
    import time
    msg_id = int(time.time() * 1000)
    
    # Asegurar que el contenido no rompa el f-string si tiene llaves (aunque es raro en el contenido del bot)
    # Una forma segura es inyectar el contenido después o escapar llaves
    safe_html = html_content.replace('{', '&#123;').replace('}', '&#125;')
    
    html_response = f'''
    <div class="chat chat-start animate-fade-in-up">
        <div class="chat-image avatar">
            <div class="w-9 h-9 rounded-full bg-gradient-to-br from-cyan-500/20 to-blue-600/20 p-1 border border-white/10 shadow-lg backdrop-blur-md">
                <img src="/static/favicon.ico" alt="IA" class="filter drop-shadow-[0_0_8px_rgba(34,211,238,0.6)] object-contain" />
            </div>
        </div>
        <div class="chat-header text-[10px] font-medium text-cyan-400/80 mb-1 ml-1 uppercase tracking-wider">
            LUKA - Asistente
        </div>
        <div class="chat-bubble bg-gradient-to-b from-white/10 to-white/5 text-gray-100 backdrop-blur-xl shadow-2xl shadow-black/40 border border-white/10 text-sm leading-relaxed px-4 py-3 rounded-2xl rounded-tl-none max-w-[85%] relative overflow-hidden group/bubble">
            <div class="absolute inset-0 bg-gradient-to-tr from-cyan-500/5 to-transparent opacity-0 group-hover/bubble:opacity-100 transition-opacity duration-500 pointer-events-none"></div>
            {safe_html}
        </div>
        <div class="chat-footer mt-2 flex items-center gap-3">
            <button type="button" id="auto-play-btn-{msg_id}" onclick="playTTS(`{bot_reply_escaped_js}`, this)" class="tts-play-btn text-gray-400 hover:text-cyan-400 text-[10px] flex items-center gap-1.5 transition-all duration-300 bg-white/5 hover:bg-white/10 rounded-full px-3 py-1 border border-white/10 hover:border-cyan-500/40 cursor-pointer shadow-sm group/btn">
                <i class="bi bi-volume-up-fill text-xs group-hover/btn:scale-110 transition-transform"></i>
                <span>Escuchar</span>
            </button>
            <span class="text-[9px] text-gray-500 italic flex items-center gap-1">
                <span class="w-1 h-1 rounded-full bg-green-500 animate-pulse"></span>
                IA Voice
            </span>
        </div>
        
        <script>
            setTimeout(() => {{
                const btn = document.getElementById('auto-play-btn-{msg_id}');
                const autoPlayEnabled = localStorage.getItem('tts-autoplay') !== 'false';
                if (btn && typeof playTTS === 'function' && autoPlayEnabled) {{
                    playTTS(`{bot_reply_escaped_js}`, btn);
                }}
            }}, 400);
        </script>
    </div>
    '''
    
    return HTMLResponse(content=html_response)
    

# --- ENDPOINT GENERADOR DE DOCUMENTOS DINÁMICOS ---
from pydantic import BaseModel, Field

class DynamicFieldsRequest(BaseModel):
    description: str

class DynamicFieldItem(BaseModel):
    name: str = Field(description="Nombre técnico de la variable (ej: nombre_arrendador)")
    label: str = Field(description="Etiqueta visible legible en español (ej: Nombre del Arrendador)")
    type: str = Field(description="Tipo de campo HTML: 'text', 'textarea', 'date', 'email', 'tel', 'number'")
    placeholder: str = Field(description="Ejemplo orientativo de valor a ingresar (ej: ej. Juan Pérez)")

class DynamicFieldsResponse(BaseModel):
    success: bool
    fields: List[DynamicFieldItem]
    template_filename: Optional[str] = None

@router.post("/api/ai/dynamic-fields", response_model=DynamicFieldsResponse)
async def generate_dynamic_fields(
    payload: DynamicFieldsRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Genera un listado de variables recomendadas en español para un tipo de documento
    personalizado mediante la API de Gemini (Structured Outputs), y pre-crea una plantilla base Jinja.
    """
    # Validar autenticación básica si se proporciona token
    if authorization and authorization.lower().startswith('bearer '):
        try:
            token = authorization.split(' ', 1)[1]
            jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except Exception:
            raise HTTPException(status_code=401, detail="Sesión inválida o expirada.")
            
    try:
        # Prompt enfocado al ámbito del LegalTech colombiano de nivel senior
        prompt = f"""
        Eres un Abogado Senior y Asesor Legal experto en la legislación colombiana y diseñador de contratos.
        El usuario desea redactar el siguiente tipo de documento personalizado: "{payload.description}".
        
        Tu tarea consiste en realizar dos cosas:
        1. Identificar de 6 a 12 variables lógicas (campos) estrictamente necesarios para este documento (nombres de las partes, documentos, objeto, plazos, valores, cláusula penal, domicilio contractual).
        2. Escribir una plantilla base legal completa, formal y muy estructurada de dicho documento en formato Markdown, utilizando la sintaxis de variables de Jinja2 (ej: {{ nombre_arrendador }}, {{ valor_canon }}, etc.) correspondientes a las variables que definiste en el paso 1.
        
        Debes estructurar el contrato con todas las formalidades de la ley colombiana, fundamentando cláusulas complejas en la normativa vigente.
        
        Retorna el resultado estrictamente en el siguiente formato JSON:
        {{
            "fields": [
                {{
                    "name": "nombre_técnico_en_minúsculas_con_guiones_bajos",
                    "label": "Etiqueta legible en español",
                    "type": "text/textarea/date/email/tel/number",
                    "placeholder": "Ejemplo de valor en Colombia"
                }}
            ],
            "template_markdown": "# CONTRATO DE...\\n\\nEn la ciudad de... Entre los suscritos..."
        }}
        """
        
        gemini_payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2
            }
        }
        
        # Consumir el servicio global de Gemini
        response = await ai_service.generate_content(gemini_payload)
        
        # Extraer texto de la respuesta
        text_response = ""
        if "candidates" in response and len(response["candidates"]) > 0:
            candidate = response["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"] and len(candidate["content"]["parts"]) > 0:
                text_response = candidate["content"]["parts"][0].get("text", "")
                
        if not text_response:
            raise HTTPException(status_code=500, detail="La IA no devolvió una respuesta de campos válida.")
            
        # Parsear dinámicamente el JSON devuelto
        try:
            fields_data = json.loads(text_response)
            fields_list = []
            template_markdown = ""
            
            if isinstance(fields_data, dict):
                template_markdown = fields_data.get("template_markdown", "")
                if "fields" in fields_data:
                    fields_list = fields_data["fields"]
                elif "variables" in fields_data:
                    fields_list = fields_data["variables"]
            elif isinstance(fields_data, list):
                fields_list = fields_data
            
            # Sanitizar y validar los campos
            validated_fields = []
            for f in fields_list:
                if not isinstance(f, dict):
                    continue
                raw_name = f.get("name", "").strip().lower()
                clean_name = re.sub(r'[^a-z0-9_]', '', raw_name.replace(" ", "_"))
                label = f.get("label", "").strip()
                
                if not clean_name or not label:
                    continue
                    
                ftype = f.get("type", "text").strip().lower()
                if ftype not in ['text', 'textarea', 'date', 'email', 'tel', 'number']:
                    ftype = 'text'
                    
                validated_fields.append({
                    "name": clean_name,
                    "label": label,
                    "type": ftype,
                    "placeholder": f.get("placeholder", "").strip()
                })
                
            # Crear y guardar la plantilla temporal si tenemos el markdown
            template_filename = None
            if validated_fields and template_markdown:
                # Sanitizar la descripción para el nombre de archivo
                clean_desc = "".join([c for c in payload.description if c.isalnum() or c in (' ', '-', '_')]).strip()
                clean_desc = clean_desc.lower().replace(" ", "_")
                filename = f"{clean_desc}.md"
                
                temp_dir = os.path.join(settings.PLANTILLAS_DIR, "temp")
                if not os.path.exists(temp_dir):
                    os.makedirs(temp_dir, exist_ok=True)
                    
                temp_file_path = os.path.join(temp_dir, filename)
                with open(temp_file_path, "w", encoding="utf-8") as f:
                    f.write(template_markdown)
                    
                template_filename = f"temp/{filename}"
                logger.info(f"Plantilla temporal dinámica guardada en: {temp_file_path}")
                
            return {
                "success": True,
                "fields": validated_fields,
                "template_filename": template_filename
            }
            
        except Exception as json_err:
            logger.error(f"Error parseando JSON dinámico de campos: {json_err}. Respuesta: {text_response}")
            raise HTTPException(status_code=500, detail="Error al decodificar la estructura de campos recomendada por la IA.")
            
    except Exception as e:
        logger.error(f"Error en generate_dynamic_fields: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/ai/secretary_error_fallback", response_class=HTMLResponse)
async def fallback():
    # Helper por si algo falla en el frontend
    pass
