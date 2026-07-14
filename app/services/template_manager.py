import os
import io
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

import jinja2
from jinja2 import meta
from docxtpl import DocxTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.core.config import settings

logger = logging.getLogger(__name__)


class TemplateManager:
    """Clase para unificar el manejo de plantillas en BD y Sistema de Archivos."""

    @staticmethod
    async def get_all_templates_from_db(session: AsyncSession) -> List[str]:
        """Obtiene todos los nombres de plantillas desde la BD."""
        result = await session.execute(select(Template).order_by(Template.filename))
        templates = result.scalars().all()
        return [t.filename for t in templates]

    @staticmethod
    async def get_all_templates_combined(session: AsyncSession) -> List[str]:
        """Obtiene nombres de plantillas únicos combinando DB y el directorio local."""
        db_templates = await TemplateManager.get_all_templates_from_db(session)
        db_templates_existing = [
            t for t in db_templates
            if os.path.exists(os.path.join(settings.PLANTILLAS_DIR, t))
        ]

        fs_templates = []
        if os.path.exists(settings.PLANTILLAS_DIR):
            fs_templates = [f for f in os.listdir(settings.PLANTILLAS_DIR) if f.endswith(('.docx', '.md'))]

        return sorted(list(set(db_templates_existing + fs_templates)))

    @staticmethod
    async def get_templates_json(session: AsyncSession) -> List[Dict[str, Any]]:
        """Devuelve las plantillas formateadas para el JSON del frontend."""
        result = await session.execute(select(Template))
        db_templates = result.scalars().all()
        db_filenames = {t.filename for t in db_templates}

        response = []
        for t in db_templates:
            file_path = os.path.join(settings.PLANTILLAS_DIR, t.filename)
            if os.path.exists(file_path):
                response.append({
                    "filename": t.filename,
                    "uploaded_at": t.uploaded_at.isoformat(),
                    "path": file_path
                })

        if os.path.exists(settings.PLANTILLAS_DIR):
            for f in os.listdir(settings.PLANTILLAS_DIR):
                if f.endswith(('.docx', '.md')) and f not in db_filenames:
                    file_path = os.path.join(settings.PLANTILLAS_DIR, f)
                    try:
                        stats = os.stat(file_path)
                        dt = datetime.fromtimestamp(stats.st_mtime)
                        response.append({
                            "filename": f,
                            "uploaded_at": dt.isoformat(),
                            "path": file_path,
                            "local_only": True
                        })
                    except Exception as e:
                        logger.warning(f"No se pudieron leer metadatos de {file_path}: {e}")

        return sorted(response, key=lambda x: x['filename'])

    @staticmethod
    async def add_template_to_db(
        session: AsyncSession, 
        filename: str, 
        description: str = None,
        status: str = "approved",
        uploaded_by_id: Optional[int] = None
    ) -> Template:
        """Agrega una plantilla a la BD si no existe."""
        result = await session.execute(select(Template).where(Template.filename == filename))
        existing = result.scalars().first()
        if existing:
            return existing

        new_template = Template(
            filename=filename, 
            description=description,
            status=status,
            uploaded_by_id=uploaded_by_id
        )
        session.add(new_template)
        await session.commit()
        await session.refresh(new_template)
        return new_template

    @staticmethod
    async def delete_template(session: AsyncSession, filename: str) -> bool:
        """Borra la plantilla de la BD y opcionalmente del sistema de archivos."""
        result = await session.execute(select(Template).where(Template.filename == filename))
        template = result.scalars().first()

        deleted_from_db = False
        if template:
            await session.delete(template)
            await session.commit()
            deleted_from_db = True

        deleted_from_fs = False
        file_path = os.path.join(settings.PLANTILLAS_DIR, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_from_fs = True
        except Exception as e:
            logger.warning(f"Se borró de BD pero no de FS {file_path}: {e}")

        return deleted_from_db or deleted_from_fs

    @staticmethod
    def resolve_template_path(filename: str) -> Optional[str]:
        """Resuelve la ruta absoluta de una plantilla buscando en varios lugares."""
        # 1. Main dir (Exact match)
        path = os.path.join(settings.PLANTILLAS_DIR, filename)
        if os.path.exists(path):
            return path

        # 2. Try extensions if not present
        for ext in ['.docx', '.md']:
            if not filename.endswith(ext):
                path_ext = os.path.join(settings.PLANTILLAS_DIR, f"{filename}{ext}")
                if os.path.exists(path_ext):
                    return path_ext

        # 3. Temp dir (Exact match)
        temp_path = os.path.join(settings.PLANTILLAS_DIR, "temp", filename)
        if os.path.exists(temp_path):
            return temp_path

        return None

    @staticmethod
    def get_template_variables(template_path: str = None, content_bytes: bytes = None, filename_hint: str = None) -> List[str]:
        """Extrae las variables Jinja2/DocxTemplate de una plantilla."""
        variables = []

        if template_path:
            filename = os.path.basename(template_path)
        elif filename_hint:
            filename = filename_hint
            if not content_bytes and not template_path:
                resolved = TemplateManager.resolve_template_path(filename)
                if resolved:
                    template_path = resolved
        else:
            return []

        if not template_path and not content_bytes:
            return []

        try:
            if filename.endswith(".docx"):
                template_source = io.BytesIO(content_bytes) if content_bytes else template_path
                if not template_source:
                    return []
                try:
                    template_obj = DocxTemplate(template_source)
                    variables = sorted(list(template_obj.get_undeclared_template_variables()))
                except Exception as e:
                    logger.warning(f"Error reading docx variables: {e}")
                    return []

            elif filename.endswith(".md"):
                if content_bytes:
                    content = content_bytes.decode('utf-8')
                elif template_path:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                else:
                    return []
                env = jinja2.Environment()
                # Registrar filtros dummy personalizados para evitar excepciones de compilación del AST
                env.filters['fecha_larga'] = lambda val: val
                env.filters['currency_cop'] = lambda val: val
                
                ast = env.parse(content)
                variables = sorted(list(meta.find_undeclared_variables(ast)))
        except Exception as e:
            logger.warning(f"Fallo extrayendo variables '{filename}': {e}. Devolviendo [].")
            return []

        return variables

    @staticmethod
    def classify_template_fields(variables: List[str]) -> List[Dict[str, Any]]:
        """
        Clasifica y formatea variables de una plantilla para generar inputs HTML apropiados.
        """
        fields = []
        for var in variables:
            # Generar una etiqueta amigable
            label = var.replace("_", " ").strip().title()
            
            # Clasificación inteligente basada en el nombre de la variable
            var_lower = var.lower()
            var_words = var_lower.split("_")
            
            field_type = "text"
            placeholder = f"Ingrese {label.lower()}"
            
            # 0. Exclusión de variables en letras (ej: valor_letras, canon_en_letras)
            if any(k in var_lower for k in ["letras", "letra"]):
                field_type = "text"
                placeholder = f"Ingrese {label.lower()}"
                
            # 1. Fechas
            elif any(k in var_lower for k in ["fecha", "date", "plazo"]):
                field_type = "date"
                placeholder = "Seleccione una fecha"
                
            # 2. Correo electrónico
            elif any(k in var_lower for k in ["correo", "email", "mail"]):
                field_type = "email"
                placeholder = "ejemplo@dominio.com"
                
            # 3. Teléfono / Celular
            elif any(k in var_words for k in ["tel", "phone"]) or any(k in var_lower for k in ["telefono", "celular", "movil"]):
                field_type = "tel"
                placeholder = "Ej: +57 300 123 4567"
                
            # 4. Números, valores monetarios y cantidades (Filtrado estricto para evitar falsos positivos de "cc" y "nit" en "accionante")
            elif (
                any(k in var_words for k in ["cc", "nit"]) or 
                any(k in var_lower for k in ["monto", "valor", "canon", "precio", "salario", "pago", "costo", "numero", "cantidad", "identificacion", "cedula"])
            ):
                field_type = "number"
                placeholder = "Ingrese un valor numérico"
                if any(k in var_words for k in ["cc", "nit"]) or any(k in var_lower for k in ["identificacion", "cedula"]):
                    placeholder = "Ingrese número de documento"
                elif any(k in var_lower for k in ["monto", "valor", "canon", "precio", "salario", "pago", "costo"]):
                    placeholder = "Ingrese valor en pesos ($)"
                
            # 5. Texto largo (textarea)
            elif any(k in var_lower for k in ["objeto", "descripcion", "clausula", "observaciones", "detalle", "direccion", "texto", "cuerpo"]):
                field_type = "textarea"
                placeholder = f"Escriba aquí los detalles de {label.lower()}..."
                
            fields.append({
                "name": var,
                "type": field_type,
                "label": label,
                "placeholder": placeholder
            })
            
        return fields

    @staticmethod
    def detect_signers_from_variables(variables: List[str]) -> List[Dict[str, Any]]:
        """
        Analiza las variables de una plantilla y agrupa de forma inteligente
        requerimientos de firma (parejas nombre/firma y correo/email, o variables huérfanas)
        para proponer firmantes de forma automatizada en el widget de STAR-DOC.
        """
        name_keywords = ["nombre", "name", "fullname", "firmante", "firma", "representante", "rep_legal"]
        email_keywords = ["correo", "email", "mail"]
        
        email_vars = []
        name_vars = []
        
        exclude_keywords = [
            "lugar", "fecha", "ciudad", "hora", "dia", "mes", "año", "anio", 
            "ubicacion", "place", "date", "city", "time", "date_firma"
        ]
        
        for var in variables:
            var_lower = var.lower()
            # Si contiene alguna palabra de exclusión de metadatos, no la procesamos como firmante
            if any(x in var_lower for x in exclude_keywords):
                continue
            if any(k in var_lower for k in email_keywords):
                email_vars.append(var)
            elif any(k in var_lower for k in name_keywords):
                name_vars.append(var)
                
        signers = []
        used_name_vars = set()
        used_email_vars = set()
        
        # 1. Emparejar variables de correo y nombre que tengan prefijos similares
        for e_var in email_vars:
            e_lower = e_var.lower()
            prefix = e_lower
            for k in email_keywords:
                prefix = prefix.replace(k, "")
            prefix = prefix.strip("_").strip("-")
            
            best_match = None
            for n_var in name_vars:
                if n_var in used_name_vars:
                    continue
                n_lower = n_var.lower()
                n_prefix = n_lower
                for k in name_keywords:
                    n_prefix = n_prefix.replace(k, "")
                n_prefix = n_prefix.strip("_").strip("-")
                
                if prefix == n_prefix or prefix in n_lower or n_prefix in e_lower:
                    best_match = n_var
                    break
            
            if best_match:
                used_name_vars.add(best_match)
                used_email_vars.add(e_var)
                role_name = prefix.replace("_", " ").replace("-", " ").strip().title()
                if not role_name or role_name.isdigit():
                    role_name = f"Firmante {role_name}" if role_name else "Firmante"
                
                signers.append({
                    "role": role_name,
                    "name_var": best_match,
                    "email_var": e_var
                })
        
        # 2. Agregar variables de correo huérfanas (sin variable de nombre explícita)
        for e_var in email_vars:
            if e_var in used_email_vars:
                continue
            e_lower = e_var.lower()
            prefix = e_lower
            for k in email_keywords:
                prefix = prefix.replace(k, "")
            prefix = prefix.strip("_").strip("-")
            
            role_name = prefix.replace("_", " ").replace("-", " ").strip().title()
            if not role_name or role_name.isdigit():
                role_name = f"Firmante {role_name}" if role_name else "Firmante"
                
            signers.append({
                "role": role_name,
                "name_var": None,
                "email_var": e_var
            })
            used_email_vars.add(e_var)
            
        # 3. Agregar variables de firma/nombre huérfanas (sin variable de correo explícita)
        for n_var in name_vars:
            if n_var in used_name_vars:
                continue
            n_lower = n_var.lower()
            prefix = n_lower
            for k in name_keywords:
                prefix = prefix.replace(k, "")
            prefix = prefix.strip("_").strip("-")
            
            role_name = prefix.replace("_", " ").replace("-", " ").strip().title()
            if not role_name or role_name.isdigit():
                role_name = f"Firmante {role_name}" if role_name else "Firmante"
                
            signers.append({
                "role": role_name,
                "name_var": n_var,
                "email_var": None
            })
            used_name_vars.add(n_var)
            
        return signers

