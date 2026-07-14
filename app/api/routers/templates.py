"""Router para gestión de plantillas."""
import os
import shutil
import logging
import asyncio
import json
import html
import re
from typing import List

import mammoth

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Body
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from googleapiclient.errors import HttpError
from googleapiclient.discovery import build

from app.auth import get_current_active_user, is_admin_user, get_creds_for_user
from app.models.user import User
from app.database import get_session
from app.services.template_manager import TemplateManager
from app.core.config import settings
from app.core.utils import sanitize_filename
from app.exceptions import TemplateNotFoundError, ValidationError, DatabaseError
from app.core.redis_client import redis_manager

logger = logging.getLogger(__name__)

async def clear_templates_cache():
    try:
        pool = await redis_manager.get_pool(db=2)
        await pool.delete("templates:list:senior")
        await pool.delete("templates:list:junior")
        await pool.delete("autocomplete:templates")
        # Eliminar las claves personalizadas de cada junior
        async for key in pool.scan_iter("templates:list:junior:*"):
            await pool.delete(key)
    except Exception as ex:
        logger.warning(f"Error al invalidar caché de templates en Redis: {ex}")

router = APIRouter(tags=["Templates Engine"])

async def is_admin_or_senior_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Verifica si el usuario es Administrador o tiene un rol Senior/Compliance."""
    from app.api.routers.documents import is_user_senior
    from fastapi import status
    if not is_user_senior(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operación restringida. Se requieren privilegios de Administrador o revisor Senior de cumplimiento."
        )
    return current_user


@router.get("/templates", response_class=JSONResponse)
async def get_templates_json(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Obtiene las plantillas disponibles filtrando por estado 'approved' para Juniors o pendientes propias."""
    from app.api.routers.documents import is_user_senior
    senior_mode = is_user_senior(current_user)
    cache_key = "templates:list:senior" if senior_mode else f"templates:list:junior:{current_user.id}"

    try:
        # Intentar leer de Redis (DB 2)
        try:
            pool = await redis_manager.get_pool(db=2)
            cached = await pool.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as ex:
            logger.warning(f"Error al leer caché de templates de Redis: {ex}")

        # Cache miss: Obtener lista base
        raw_templates = await TemplateManager.get_templates_json(session)

        # Mapear estados y propietarios desde la base de datos
        from sqlalchemy import select
        from app.models.template import Template
        res = await session.execute(select(Template))
        db_templates = res.scalars().all()
        status_map = {t.filename: t.status for t in db_templates}
        comments_map = {t.filename: t.comments for t in db_templates}
        id_map = {t.filename: t.id for t in db_templates}
        uploaded_by_map = {t.filename: t.uploaded_by_id for t in db_templates}

        filtered_response = []
        for item in raw_templates:
            filename = item["filename"]
            status = status_map.get(filename, "approved")
            comments = comments_map.get(filename, None)
            template_id = id_map.get(filename, None)
            uploaded_by = uploaded_by_map.get(filename, None)
            
            # Senior ve todo. Junior ve las aprobadas o las que él mismo subió (pendientes o rechazadas)
            if senior_mode or status == "approved" or (uploaded_by == current_user.id):
                item["status"] = status
                item["comments"] = comments
                item["id"] = template_id
                filtered_response.append(item)

        # Escribir en Redis
        try:
            pool = await redis_manager.get_pool(db=2)
            await pool.setex(cache_key, 300, json.dumps(filtered_response))
        except Exception as ex:
            logger.warning(f"Error al guardar caché de templates en Redis: {ex}")

        return filtered_response
    except Exception as e:
        logger.error(f"Error obteniendo templates: {e}")
        raise DatabaseError(f"Error interno: {e}")


@router.get("/templates-list/md", response_class=JSONResponse)
async def get_md_templates_list(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Obtiene solo las plantillas Markdown."""
    try:
        all_templates = await TemplateManager.get_all_templates_combined(session)
        md_templates = [t for t in all_templates if t.endswith('.md')]
        return {"success": True, "templates": sorted(md_templates)}
    except Exception as e:
        logger.error(f"Error obteniendo templates MD: {e}")
        raise DatabaseError(f"Error interno: {e}")


@router.post("/upload-template")
async def upload_template(
    template_file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Sube una nueva plantilla (abierta a Juniors con aprobación pendiente)."""
    if not (template_file.filename.endswith('.docx') or template_file.filename.endswith('.md')):
        raise ValidationError("filename", "Formato de archivo no válido. Use .docx o .md")

    safe_filename = sanitize_filename(template_file.filename)
    if template_file.filename.endswith('.docx') and not safe_filename.endswith('.docx'):
        safe_filename += '.docx'
    elif template_file.filename.endswith('.md') and not safe_filename.endswith('.md'):
        safe_filename += '.md'

    file_path = os.path.join(settings.PLANTILLAS_DIR, safe_filename)

    # Verificar si ya existe en la BD
    from sqlalchemy import select
    from app.models.template import Template
    result = await session.execute(select(Template).where(Template.filename == safe_filename))
    if result.scalars().first():
        raise ValidationError("filename", f"La plantilla '{safe_filename}' ya existe.")

    # Determinar si el usuario es Senior/Admin
    from app.api.routers.documents import is_user_senior
    is_senior = is_user_senior(current_user)
    status = "approved" if is_senior else "pending_approval"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(template_file.file, buffer)

        await TemplateManager.add_template_to_db(
            session=session, 
            filename=safe_filename, 
            description=f"Subida por {current_user.username}",
            status=status,
            uploaded_by_id=current_user.id
        )
        
        # Invalidar caché en Redis
        await clear_templates_cache()
            
        msg = f"Plantilla '{safe_filename}' subida con éxito y aprobada de inmediato." if is_senior else f"Plantilla '{safe_filename}' subida con éxito. Queda en estado pendiente de aprobación por el equipo de cumplimiento."
        return {"success": True, "message": msg}
    except Exception as e:
        logger.error(f"Error subiendo template: {e}")
        raise DatabaseError(f"No se pudo subir la plantilla: {e}")


@router.delete("/delete-template/{template_name}")
async def delete_template(
    template_name: str,
    current_user: User = Depends(is_admin_or_senior_user),
    session: AsyncSession = Depends(get_session)
):
    """Elimina una plantilla (admin only)."""
    success = await TemplateManager.delete_template(session, template_name)
    if not success:
        raise TemplateNotFoundError(template_name)
        
    # Invalidar caché en Redis
    await clear_templates_cache()
        
    return {"success": True, "message": f"Plantilla '{template_name}' eliminada."}


@router.get("/template-content/{template_name}")
async def get_template_content(
    template_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtiene el contenido de una plantilla MD."""
    if not template_name.endswith('.md'):
        raise ValidationError("template_name", "Solo se permiten archivos .md")
    
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


@router.post("/template-content/{template_name}")
async def save_template_content(
    template_name: str,
    request: Request,
    current_user: User = Depends(is_admin_or_senior_user)
):
    """Guarda el contenido de una plantilla MD (admin only)."""
    if not template_name.endswith('.md'):
        raise ValidationError("template_name", "Solo se permiten archivos .md")
    
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
    
    content = await request.body()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.decode('utf-8'))
        
    # Invalidar caché de templates en Redis
    await clear_templates_cache()
        
    return {"success": True}


@router.post("/create-template-from-ia")
async def create_template_from_ia(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """Crea una plantilla desde el output de IA (abierta a Juniors con aprobación pendiente)."""
    data = await request.json()
    fname = data.get('filename')
    content = data.get('content')
    
    if not fname or not content:
        raise ValidationError("body", "Faltan datos (filename o content)")
    
    if not fname.endswith('.md'):
        raise ValidationError("filename", "El archivo debe ser .md")
    
    path = os.path.join(settings.PLANTILLAS_DIR, os.path.basename(fname))
    if os.path.exists(path):
        raise ValidationError("filename", "Ya existe un archivo con ese nombre")
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    from app.api.routers.documents import is_user_senior
    is_senior = is_user_senior(current_user)
    status = "approved" if is_senior else "pending_approval"
    
    await TemplateManager.add_template_to_db(
        session=session, 
        filename=os.path.basename(fname), 
        description=f"Creado con IA por {current_user.username}",
        status=status,
        uploaded_by_id=current_user.id
    )
    
    await clear_templates_cache()
    
    msg = "Plantilla de IA guardada y aprobada con éxito." if is_senior else "Plantilla de IA guardada con éxito. Pendiente de aprobación por un revisor Senior."
    return {"success": True, "message": msg}


@router.get("/template-html/{template_name}")
async def get_template_html(
    template_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtiene el contenido HTML de una plantilla DOCX."""
    if not template_name.endswith('.docx'):
        raise ValidationError("template_name", "Solo se permiten archivos .docx")
    
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
    
    with open(path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        html = result.value
        return {"success": True, "html": html}


@router.post("/save-docx-template")
async def save_docx_template(
    request: Request,
    current_user: User = Depends(is_admin_or_senior_user)
):
    """Guarda el HTML editado como un DOCX."""
    data = await request.json()
    template_name = data.get("template_name")
    html_content = data.get("html_content")
    
    if not template_name or not html_content:
        raise ValidationError("body", "Faltan datos (template_name o html_content)")
        
    # Decodificar entidades HTML de Jinja2 y normalizar espacios
    html_content = html.unescape(html_content)
    html_content = re.sub(r'\{\s+\{', '{{', html_content)
    html_content = re.sub(r'\}\s+\}', '}}', html_content)
        
    if not template_name.endswith('.docx'):
        raise ValidationError("template_name", "Solo se permiten archivos .docx")
        
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
        
    # Verificar que las etiquetas Jinja coincidan
    open_tags = html_content.count("{{")
    close_tags = html_content.count("}}")
    if open_tags != close_tags:
        raise ValidationError("html_content", "Hay etiquetas Jinja2 {{ abiertas sin cerrar }}")
        
    # Versionamiento (.bak)
    bak_path = path + ".bak"
    if os.path.exists(path):
        shutil.copy2(path, bak_path)
    
    try:
        from html2docx import html2docx
        # html2docx function converts valid html to io.BytesIO
        docx_io = html2docx(html_content, title=template_name)
        with open(path, "wb") as f:
            f.write(docx_io.getvalue())
            
        # Invalidar caché de templates en Redis
        await clear_templates_cache()
            
        return {"success": True, "message": "Plantilla actualizada correctamente."}
    except Exception as e:
        if os.path.exists(bak_path):
            shutil.copy2(bak_path, path)
        raise ValidationError("html_content", f"Error en la conversión: {str(e)}")
 
 
@router.post("/restore-docx-template/{template_name}")
async def restore_docx_template(
    template_name: str,
    current_user: User = Depends(is_admin_or_senior_user)
):
    """Restaura una plantilla DOCX desde su archivo .bak (si existe)."""
    if not template_name.endswith('.docx'):
        raise ValidationError("template_name", "Solo aplicable a archivos .docx")
        
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    bak_path = path + ".bak"
    
    if not os.path.exists(bak_path):
        raise ValidationError("template_name", "No se encontró copia de seguridad (.bak) para esta plantilla.")
        
    try:
        shutil.copy2(bak_path, path)
        
        # Invalidar caché de templates en Redis
        await clear_templates_cache()
            
        return {"success": True, "message": "Plantilla restaurada correctamente desde su versión anterior."}
    except Exception as e:
        raise ValidationError("template_name", f"Error restaurando: {str(e)}")


@router.get("/template-variables/{template_name}")
async def get_variables_api(
    template_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtiene las variables presentes en una plantilla (MD o DOCX)."""
    from app.services.template_manager import TemplateManager
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
    
    vars_list = TemplateManager.get_template_variables(path)
    return {"success": True, "variables": vars_list}


@router.post("/template-variables-from-drive")
async def get_variables_from_drive(
    google_doc_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Extrae variables de un documento de Google Drive.
    Descarga el Google Doc como .docx y extrae las variables {{...}}.
    """
    if not google_doc_id:
        raise HTTPException(400, "google_doc_id es requerido")

    creds = await get_creds_for_user(current_user, session)
    if not creds:
        raise HTTPException(400, "Google no conectado. Autentica primero.")

    try:
        drive_service = build('drive', 'v3', credentials=creds)

        # Obtener metadata del archivo
        file_meta = await asyncio.to_thread(
            lambda: drive_service.files().get(fileId=google_doc_id, fields='name').execute()
        )
        template_filename = file_meta.get('name', 'google_doc') + ".docx"

        # Exportar como .docx
        content = await asyncio.to_thread(
            lambda: drive_service.files().export_media(
                fileId=google_doc_id,
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ).execute()
        )

        # Extraer variables
        vars_list = TemplateManager.get_template_variables(
            content_bytes=content,
            filename_hint=template_filename
        )

        return {
            "success": True,
            "variables": vars_list,
            "filename": template_filename
        }

    except HttpError as e:
        logger.error(f"Error Drive al extraer variables: {e}")
        raise HTTPException(500, f"Error accediendo al documento: {str(e)}")
    except Exception as e:
        logger.error(f"Error inesperado extrayendo variables de Drive: {e}")
        raise HTTPException(500, f"Error extrayendo variables: {str(e)}")


@router.get("/template-fields/{template_name}")
async def get_fields_api(
    template_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """Obtiene los campos clasificados dinámicamente presentes en una plantilla local."""
    path = os.path.join(settings.PLANTILLAS_DIR, template_name)
    if not os.path.exists(path):
        raise TemplateNotFoundError(template_name)
    
    vars_list = TemplateManager.get_template_variables(path)
    fields = TemplateManager.classify_template_fields(vars_list)
    
    # Enriquecer campos si existe un archivo JSON condicional complementario
    base_name, _ = os.path.splitext(template_name)
    json_filename = base_name + ".json"
    json_path = os.path.join(settings.PLANTILLAS_DIR, json_filename)
    
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            
            if isinstance(json_data, dict) and "variables" in json_data:
                vars_config = json_data["variables"]
                existing_names = {field["name"] for field in fields}
                
                # 1. Enriquecer campos existentes
                for field in fields:
                    field_name = field.get("name")
                    if field_name in vars_config:
                        cfg = vars_config[field_name]
                        if isinstance(cfg, dict):
                            if "type" in cfg:
                                field["type"] = cfg["type"]
                            if "label" in cfg:
                                field["label"] = cfg["label"]
                            if "placeholder" in cfg:
                                field["placeholder"] = cfg["placeholder"]
                            if "options" in cfg:
                                field["options"] = cfg["options"]
                            if "depends_on" in cfg:
                                field["depends_on"] = cfg["depends_on"]
                                
                # 2. Inyectar campos virtuales condicionales del JSON
                for field_name, cfg in vars_config.items():
                    if field_name not in existing_names and isinstance(cfg, dict):
                        label = cfg.get("label", field_name.replace("_", " ").strip().title())
                        new_field = {
                            "name": field_name,
                            "type": cfg.get("type", "text"),
                            "label": label,
                            "placeholder": cfg.get("placeholder", f"Ingrese {label.lower()}")
                        }
                        if "options" in cfg:
                            new_field["options"] = cfg["options"]
                        if "depends_on" in cfg:
                            new_field["depends_on"] = cfg["depends_on"]
                        fields.append(new_field)
        except Exception as e:
            logger.error(f"Error procesando JSON de configuracion condicional {json_filename}: {e}")
            
    detected_signers = TemplateManager.detect_signers_from_variables(vars_list)
    return {"success": True, "fields": fields, "detected_signers": detected_signers}




@router.post("/template-fields-from-drive")
async def get_fields_from_drive(
    google_doc_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Extrae variables de un documento de Google Drive y las devuelve
    clasificadas dinámicamente para inputs HTML.
    """
    if not google_doc_id:
        raise HTTPException(400, "google_doc_id es requerido")

    creds = await get_creds_for_user(current_user, session)
    if not creds:
        raise HTTPException(400, "Google no conectado. Autentica primero.")

    try:
        drive_service = build('drive', 'v3', credentials=creds)

        # Obtener metadata del archivo
        file_meta = await asyncio.to_thread(
            lambda: drive_service.files().get(fileId=google_doc_id, fields='name').execute()
        )
        template_filename = file_meta.get('name', 'google_doc') + ".docx"

        # Exportar como .docx
        content = await asyncio.to_thread(
            lambda: drive_service.files().export_media(
                fileId=google_doc_id,
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ).execute()
        )

        # Extraer variables
        vars_list = TemplateManager.get_template_variables(
            content_bytes=content,
            filename_hint=template_filename
        )
        
        fields = TemplateManager.classify_template_fields(vars_list)
        detected_signers = TemplateManager.detect_signers_from_variables(vars_list)

        return {
            "success": True,
            "fields": fields,
            "filename": template_filename,
            "detected_signers": detected_signers
        }

    except HttpError as e:
        logger.error(f"Error Drive al extraer campos: {e}")
        raise HTTPException(500, f"Error accediendo al documento: {str(e)}")
    except Exception as e:
        logger.error(f"Error inesperado extrayendo campos de Drive: {e}")
        raise HTTPException(500, f"Error extrayendo campos: {str(e)}")


# --- WORKFLOW DE APROBACIÓN DE PLANTILLAS ---
from pydantic import BaseModel
from typing import Optional

class TemplateReviewInput(BaseModel):
    action: str  # approve | reject
    comments: Optional[str] = None

@router.post("/api/templates/{template_id}/review")
async def review_template(
    template_id: int,
    payload: TemplateReviewInput,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(is_admin_or_senior_user)
):
    """
    Aprueba o rechaza una plantilla subida por un Junior (revisión de Oficial Senior).
    """
    from app.models.template import Template
    template = await session.get(Template, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")

    action = payload.action.lower()
    if action == "approve":
        template.status = "approved"
        template.comments = payload.comments or "Aprobada por equipo Senior."
    elif action == "reject":
        if not payload.comments or not payload.comments.strip():
            raise HTTPException(status_code=400, detail="Debe ingresar obligatoriamente comentarios/motivos para rechazar la plantilla.")
        template.status = "rejected"
        template.comments = payload.comments
    else:
        raise HTTPException(status_code=400, detail="Acción no válida. Use 'approve' o 'reject'.")

    session.add(template)
    await session.commit()
    await session.refresh(template)

    # Invalidar caché en Redis
    await clear_templates_cache()

    return {
        "success": True,
        "message": f"Plantilla revisada exitosamente. Estado: {template.status}",
        "status": template.status
    }

