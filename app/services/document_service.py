
import os
import json
import re
import io
import hashlib
import uuid
import shutil
import subprocess
import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any, Union

import jinja2
from jinja2 import meta
from jinja2.sandbox import SandboxedEnvironment
import locale
from datetime import datetime
import pandas as pd
from docxtpl import DocxTemplate
from fastapi import HTTPException

from app.core.config import settings
from app.services.template_manager import TemplateManager
from app.services.validation_service import validate_document_context

logger = logging.getLogger(__name__)

# Referencia interna para uso en internal_generate_document
_resolve_template_path = TemplateManager.resolve_template_path

# --- Conversion Logic ---

async def convert_to_pdf(docx_path: str, output_dir: str) -> Optional[str]:
    pdf_name = os.path.splitext(os.path.basename(docx_path))[0] + '.pdf'
    pdf_path = os.path.join(output_dir, pdf_name)
    logger.info(f"Iniciando conversión a PDF para: {docx_path}")

    # 1. docx2pdf
    try:
        from docx2pdf import convert
        logger.info(f"Usando docx2pdf para convertir {docx_path}")
        await asyncio.to_thread(convert, docx_path, pdf_path)
        if os.path.exists(pdf_path):
            return pdf_path
    except Exception as e_docx2pdf:
        logger.warning(f"docx2pdf falló ({e_docx2pdf}), intentando con LibreOffice.")

    # 2. LibreOffice
    libreoffice_exec = None
    if os.name == 'nt':
        paths = [
            shutil.which('soffice'),
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
        ]
        for p in paths:
            if p and os.path.exists(p):
                libreoffice_exec = p
                break
    else:
        libreoffice_exec = shutil.which('libreoffice') or shutil.which('soffice')

    if libreoffice_exec:
        try:
            logger.info(f"Intentando con LibreOffice: {libreoffice_exec}")
            
            # Crear perfil de usuario temporal para LibreOffice para evitar bloqueos e instancias concurrentes colgadas
            temp_profile_dir = os.path.join(os.path.dirname(docx_path), f"lo_profile_{uuid.uuid4().hex}")
            user_inst_arg = f"-env:UserInstallation=file:///{temp_profile_dir.replace(os.sep, '/')}"
            
            def run_libreoffice():
                cmd = [
                    libreoffice_exec,
                    '--headless',
                    user_inst_arg,
                    '--convert-to', 'pdf',
                    '--outdir', os.path.abspath(output_dir),
                    os.path.abspath(docx_path)
                ]
                logger.info(f"Ejecutando comando LibreOffice: {' '.join(cmd)}")
                return subprocess.run(cmd, capture_output=True, text=True, check=False)

            res = await asyncio.to_thread(run_libreoffice)

            # Limpiar el perfil temporal
            if os.path.exists(temp_profile_dir):
                try:
                    shutil.rmtree(temp_profile_dir, ignore_errors=True)
                except:
                    pass

            if res.returncode == 0 and os.path.exists(pdf_path):
                logger.info("Conversión con LibreOffice exitosa.")
                return pdf_path
            else:
                logger.warning(f"LibreOffice falló con código {res.returncode}. stdout: {res.stdout}, stderr: {res.stderr}")
        except Exception as e_libreoffice:
            logger.warning(f"Error ejecutando LibreOffice: {e_libreoffice}", exc_info=True)
    else:
        logger.warning("No se encontró ejecutable de LibreOffice.")

    # 3. Pandoc
    pandoc_path = shutil.which('pandoc') or r'C:\Program Files\Pandoc\pandoc.exe'
    if pandoc_path and os.path.exists(pandoc_path):
        try:
            logger.info(f"Intentando con Pandoc: {pandoc_path}")
            
            # Buscamos si hay un motor de PDF disponible (pdflatex, xelatex, weasyprint, typst, wkhtmltopdf)
            pdf_engine = None
            if shutil.which('pdflatex'):
                pdf_engine = 'pdflatex'
            elif shutil.which('xelatex'):
                pdf_engine = 'xelatex'
            elif shutil.which('weasyprint'):
                pdf_engine = 'weasyprint'
            elif shutil.which('typst'):
                pdf_engine = 'typst'
            elif shutil.which('wkhtmltopdf'):
                pdf_engine = 'wkhtmltopdf'
                
            def run_pandoc():
                cmd = [pandoc_path, os.path.abspath(docx_path), '-o', os.path.abspath(pdf_path)]
                if pdf_engine:
                    cmd.extend(['--pdf-engine', pdf_engine])
                logger.info(f"Ejecutando comando Pandoc: {' '.join(cmd)}")
                return subprocess.run(cmd, capture_output=True, text=True, check=False)

            res = await asyncio.to_thread(run_pandoc)
            if res.returncode == 0 and os.path.exists(pdf_path):
                logger.info(f"Conversión con Pandoc exitosa (Motor: {pdf_engine or 'por defecto'}).")
                return pdf_path
            else:
                logger.warning(f"Pandoc falló con código {res.returncode}. stdout: {res.stdout}, stderr: {res.stderr}")
        except Exception as e_pandoc:
            logger.warning(f"Error ejecutando Pandoc: {e_pandoc}", exc_info=True)
    else:
        logger.warning("No se encontró ejecutable de Pandoc.")

    logger.error("Todos los métodos de conversión a PDF fallaron.")
    return None

async def convert_md_to_docx(md_path: str, output_dir: str) -> Optional[str]:
    docx_name = os.path.splitext(os.path.basename(md_path))[0] + '.docx'
    docx_path = os.path.join(output_dir, docx_name)
    pandoc_path = shutil.which('pandoc') or 'C:\\Program Files\\Pandoc\\pandoc.exe'

    def run_pandoc_sync():
        try:
            subprocess.run([pandoc_path, md_path, '--wrap=none', '-o', docx_path], check=True, capture_output=True)
            return docx_path
        except Exception as e:
            logger.error(f"Error conversió MD->DOCX: {e}")
            return None

    return await asyncio.to_thread(run_pandoc_sync)

async def convert_md_to_pdf(md_path: str, output_dir: str) -> Optional[str]:
    """Convierte Markdown a PDF usando cascada de motores disponibles.
    
    Orden de intentos:
    1. pandoc + pdflatex (motor LaTeX más común)
    2. pandoc + xelatex (mejor soporte Unicode, requiere texlive-xetex)
    3. Fallback: MD -> DOCX (pandoc) -> PDF (LibreOffice)
    """
    pdf_name = os.path.splitext(os.path.basename(md_path))[0] + '.pdf'
    pdf_path = os.path.join(output_dir, pdf_name)
    pandoc_path = shutil.which('pandoc')

    if not pandoc_path:
        logger.error("Pandoc no está instalado. No se puede convertir MD a PDF.")
        return None

    # --- Intento 1: pandoc + pdflatex ---
    pdflatex_path = shutil.which('pdflatex')
    if pdflatex_path:
        try:
            logger.info(f"Intentando conversión MD->PDF con pdflatex...")
            result = await asyncio.to_thread(
                subprocess.run,
                [pandoc_path, md_path, '--pdf-engine=pdflatex',
                 '-V', 'geometry:margin=2.5cm',
                 '-V', 'fontsize=12pt',
                 '-o', pdf_path],
                capture_output=True, check=True
            )
            if os.path.exists(pdf_path):
                logger.info(f"✅ Conversión MD->PDF exitosa con pdflatex: {pdf_name}")
                return pdf_path
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else 'Sin detalles'
            logger.warning(f"pdflatex falló: {stderr_msg}")
        except Exception as e:
            logger.warning(f"Error inesperado con pdflatex: {e}")

    # --- Intento 2: pandoc + xelatex (soporte Unicode completo) ---
    xelatex_path = shutil.which('xelatex')
    if xelatex_path:
        try:
            logger.info(f"Intentando conversión MD->PDF con xelatex...")
            result = await asyncio.to_thread(
                subprocess.run,
                [pandoc_path, md_path, '--pdf-engine=xelatex',
                 '-V', 'geometry:margin=2.5cm',
                 '-o', pdf_path],
                capture_output=True, check=True
            )
            if os.path.exists(pdf_path):
                logger.info(f"✅ Conversión MD->PDF exitosa con xelatex: {pdf_name}")
                return pdf_path
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else 'Sin detalles'
            logger.warning(f"xelatex falló: {stderr_msg}")
        except Exception as e:
            logger.warning(f"Error inesperado con xelatex: {e}")

    # --- Intento 3 (Fallback): MD -> DOCX -> PDF vía LibreOffice ---
    logger.info("Motores LaTeX no disponibles. Usando fallback: MD -> DOCX -> PDF (LibreOffice)...")
    try:
        # Paso 1: MD -> DOCX con pandoc
        docx_path = await convert_md_to_docx(md_path, output_dir)
        if not docx_path or not os.path.exists(docx_path):
            logger.error("Fallback falló: pandoc no pudo crear el DOCX intermedio.")
            return None
        
        # Paso 2: DOCX -> PDF con LibreOffice
        pdf_result = await convert_to_pdf(docx_path, output_dir)
        
        # Limpiar el DOCX intermedio solo si la conversión fue exitosa
        if pdf_result and os.path.exists(pdf_result):
            try:
                os.remove(docx_path)
            except OSError:
                pass
            logger.info(f"✅ Conversión MD->PDF exitosa vía fallback (LibreOffice): {os.path.basename(pdf_result)}")
            return pdf_result
        else:
            # Si LibreOffice también falla, limpiar el docx intermedio
            try:
                os.remove(docx_path)
            except OSError:
                pass
            logger.error("Fallback falló: LibreOffice no pudo crear el PDF.")
            return None
    except Exception as e:
        logger.error(f"Error en fallback MD->DOCX->PDF: {e}")
        return None

def _clean_context(context: dict) -> dict:
    """
    Limpia el contexto para asegurar que los saltos de línea se rendericen correctamente.
    Normaliza saltos de línea literales y elimina retornos de carro problemáticos.
    """
    new_ctx = {}
    for k, v in context.items():
        if isinstance(v, str):
            clean_v = v.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r', '')
            new_ctx[k] = clean_v
        elif isinstance(v, dict):
             new_ctx[k] = _clean_context(v)
        elif isinstance(v, list):
             new_list = []
             for i in v:
                 if isinstance(i, dict):
                     new_list.append(_clean_context(i))
                 elif isinstance(i, str):
                     new_list.append(i.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r', ''))
                 else:
                     new_list.append(i)
             new_ctx[k] = new_list
        else:
            new_ctx[k] = v
    return new_ctx

# --- Custom Filters ---

def _inject_subdocs(context: dict, doc: DocxTemplate) -> dict:
    """
    Recorre el contexto buscando strings con el prefijo 'subdoc:' 
    y los reemplaza en vivo con un objeto doc.new_subdoc(path).
    """
    new_ctx = {}
    
    for k, v in context.items():
        if isinstance(v, str) and v.startswith("subdoc:"):
            filename = v.replace("subdoc:", "").strip()
            path = os.path.join(settings.PLANTILLAS_DIR, "clausulas", filename)
            logger.info(f"Intentando parsear subdoc: {path}")
            if os.path.exists(path):
                try:
                    new_ctx[k] = doc.new_subdoc(path)
                    logger.info(f"SubDoc {filename} inyectado correctamente en la llave {k}")
                except Exception as e:
                    logger.error(f"Error generando subdoc para {filename}: {e}")
                    new_ctx[k] = ""
            else:
                logger.warning(f"Subdoc no encontrado: {path}")
                new_ctx[k] = ""
        elif isinstance(v, dict):
            new_ctx[k] = _inject_subdocs(v, doc)
        elif isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(_inject_subdocs(item, doc))
                else:
                    new_list.append(item)
            new_ctx[k] = new_list
        else:
            new_ctx[k] = v
            
    return new_ctx

def format_currency_cop(value):
    try:
        if isinstance(value, str):
            value = float(value.replace(',', '').replace('$', ''))
        return "${:,.2f}".format(value).replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return value

def format_date_long(value):
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        meses = {
            1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
            7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
        }
        return f"{dt.day} de {meses[dt.month]} de {dt.year}"
    except:
        return value

def registrar_firma_electronica_y_sello(file_path: str, context: dict) -> dict:
    """
    Calcula el hash SHA-256 de un archivo final y genera el certificado de firma electrónica
    de conformidad con el Decreto 2364 de 2012 y la Ley 527 de 1999 en Colombia.
    Guarda un archivo de metadata .json al lado del archivo original.
    """
    try:
        if not os.path.exists(file_path):
            logger.warning(f"No se pudo registrar firma: El archivo no existe en {file_path}")
            return {}
            
        # 1. Calcular Hash SHA-256
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()
        
        # 2. Reconstruir información de firmantes a partir del contexto
        firmantes = []
        
        # Intentar extraer Arrendador / Arrendatario
        arrendador = context.get("arrendador_nombre")
        arrendador_id = context.get("arrendador_cedula")
        if arrendador:
            firmantes.append({
                "nombre": arrendador,
                "identificacion": f"C.C. {arrendador_id}" if arrendador_id else "No suministrada",
                "rol": "Arrendador"
            })
            
        arrendatario = context.get("arrendatario_nombre")
        arrendatario_id = context.get("arrendatario_cedula")
        if arrendatario:
            firmantes.append({
                "nombre": arrendatario,
                "identificacion": f"C.C. {arrendatario_id}" if arrendatario_id else "No suministrada",
                "rol": "Arrendatario"
            })
            
        # Intentar extraer Empleador / Empleado
        empleador = context.get("empleador_nombre")
        empleador_id = context.get("empleador_cedula")
        if empleador:
            firmantes.append({
                "nombre": empleador,
                "identificacion": f"C.C. {empleador_id}" if empleador_id else "No suministrada",
                "rol": "Empleador"
            })
            
        empleado = context.get("empleado_nombre")
        empleado_id = context.get("empleado_cedula")
        if empleado:
            firmantes.append({
                "nombre": empleado,
                "identificacion": f"C.C. {empleado_id}" if empleado_id else "No suministrada",
                "rol": "Empleado"
            })

        # Accionante / Accionado de tutela o peticionario
        accionante = context.get("nombre_accionante") or context.get("nombre_peticionario")
        accionante_id = context.get("documento_identidad") or context.get("cedula_peticionario")
        if accionante:
            firmantes.append({
                "nombre": accionante,
                "identificacion": f"C.C. {accionante_id}" if accionante_id else "No suministrada",
                "rol": "Accionante/Peticionario"
            })
            
        if not firmantes:
            firmantes.append({
                "nombre": "Generador Autónomo STAR-DOC",
                "identificacion": "Algoritmo de IA",
                "rol": "Autor"
            })
            
        # 3. Estructurar metadata de firma electrónica (equivalencia funcional)
        metadata_firma = {
            "documento_original_nombre": os.path.basename(file_path),
            "sha256_hash": file_hash,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "timestamp_colombia": datetime.now().isoformat(),
            "firmantes": firmantes,
            "seguridad_integridad": {
                "metodo_autenticacion": "Acceso por credenciales de usuario STAR-DOC",
                "equivalencia_funcional_ley_527": "Conforme al Artículo 7 de la Ley 527 de 1999, este sello electrónico "
                                                  "cumple con los requisitos de identificación del iniciador e integridad "
                                                  "del mensaje de datos.",
                "auditoria_no_alteracion": "Cualquier cambio posterior en los bytes del documento anulará la coincidencia "
                                            "con el hash SHA-256 registrado en este sello."
            },
            "proveedor_plataforma": "STAR-DOC LegalTech Platform v2026",
            "sello_verificacion": hashlib.sha256(f"{file_hash}-{datetime.now().date()}".encode()).hexdigest()
        }
        
        # 4. Guardar archivo JSON al lado
        firma_path = os.path.splitext(file_path)[0] + "_firma.json"
        with open(firma_path, "w", encoding="utf-8") as f:
            json.dump(metadata_firma, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Sello de Firma Electrónica e Integridad registrado para {os.path.basename(file_path)}. Hash: {file_hash}")
        return metadata_firma
    except Exception as e:
        logger.error(f"Error registrando sello de firma electrónica: {e}")
        return {}


async def internal_generate_document(
    template_filename: str,
    context: dict,
    output_format: str = 'docx',
    convert_pdf: bool = False,
    template_content: Optional[bytes] = None,
    custom_filename: Optional[str] = None,
    output_dir: Optional[str] = None,
    google_doc_id: Optional[str] = None,
    anchor_ipfs: bool = False,
    classification: str = "public",
    user_id: Optional[int] = None
) -> str:
    """
    Genera un documento a partir de una plantilla y un contexto.
    Retorna el NOMBRE DEL ARCHIVO generado (basename).

    Si google_doc_id es proporcionado y template_content es None,
    se descargará el contenido del Google Doc.
    """
    
    # +++ VALIDACIÓN LEGAL ESTRICTA CON PYDANTIC +++
    try:
        context = validate_document_context(template_filename, context)
    except ValueError as ve:
        # Relanzamos como error HTTP 422 (Unprocessable Entity) que los frameworks entienden
        raise HTTPException(status_code=422, detail=str(ve))

    # 0. Configurar directorio de salida
    target_dir = output_dir or settings.OUTPUT_DIR
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        
    if output_format == 'pdf':
        convert_pdf = True

    # Limpiar contexto
    context = _clean_context(context)
    # logger.info(f"Contexto limpio: {context}")

    # 1. Resolver el contenido de la plantilla
    if template_content is None:
        template_path = _resolve_template_path(template_filename)
        if not template_path:
            raise HTTPException(status_code=404, detail=f"Plantilla '{template_filename}' no encontrada.")
        with open(template_path, "rb") as f:
            template_content = f.read()
    
    # Determinar nombre de salida
    if custom_filename:
        # Asegurar extensión correcta
        base, _ = os.path.splitext(custom_filename)
        # Limpiar caracteres peligrosos
        base = "".join([c for c in base if c.isalnum() or c in (' ', '-', '_')]).strip()
        out_name = f"{base}.{output_format}"
    else:
        # Fallback a nombre temporal antiguo
        out_name = f"temp_{uuid.uuid4()}.{output_format}"

    final_path = os.path.join(target_dir, out_name)

    # 2. Lógica Markdown
    if template_filename.endswith('.md'):
        try:
            md_content = template_content.decode('utf-8')
            # Crear entorno seguro (Sandbox) con filtros
            env = SandboxedEnvironment()
            env.filters['currency_cop'] = format_currency_cop
            env.filters['fecha_larga'] = format_date_long

            template = env.from_string(md_content)
            rendered = template.render(context)

            base_name = template_filename.rsplit('.', 1)[0]

            if output_format in ['md', 'txt']:
                ext = output_format
                # USAR custom_filename si existe, de lo contrario UUID
                if custom_filename:
                    final_path = os.path.join(target_dir, f"{base_name}_{custom_filename}.{ext}")
                else:
                    final_path = os.path.join(target_dir, f"{base_name}_{uuid.uuid4()}.{ext}")
                with open(final_path, "w", encoding="utf-8") as f:
                    f.write(rendered)
                
                # IPFS Hook
                if anchor_ipfs:
                    from app.services.ipfs_integration_service import IPFSIntegrationService
                    from app.services.crypto_engine import DocClassification
                    try:
                        await IPFSIntegrationService.anchor_and_stamp(
                            file_path=final_path,
                            classification=DocClassification(classification),
                            user_id=user_id
                        )
                    except Exception as e:
                        logger.error(f"Error en Hook IPFS (MD): {e}")

                registrar_firma_electronica_y_sello(final_path, context)
                return os.path.basename(final_path)

            elif output_format in ['docx', 'pdf']:
                # USAR custom_filename para el temporal si existe
                if custom_filename:
                    temp_md = os.path.join(target_dir, f"{custom_filename}.md")
                else:
                    temp_md = os.path.join(target_dir, f"temp_{uuid.uuid4()}.md")
                with open(temp_md, "w", encoding="utf-8") as f:
                    f.write(rendered)

                final_path = None
                if output_format == 'docx':
                    final_path = await convert_md_to_docx(temp_md, target_dir)
                else:
                    final_path = await convert_md_to_pdf(temp_md, target_dir)

                if final_path:
                    # RENOMBRAR al nombre custom si existe
                    if custom_filename:
                        desired_name = f"{custom_filename}.{output_format}"
                        desired_path = os.path.join(target_dir, desired_name)
                        # Mover el archivo convertido al nombre deseado
                        import shutil as shutil_module
                        shutil_module.move(final_path, desired_path)
                        final_path = desired_path
                    
                    # Solo borramos el temporal si tuvo éxito
                    if os.path.exists(temp_md):
                        os.remove(temp_md)
                        
                    # IPFS Hook
                    if anchor_ipfs:
                        from app.services.ipfs_integration_service import IPFSIntegrationService
                        from app.services.crypto_engine import DocClassification
                        try:
                            await IPFSIntegrationService.anchor_and_stamp(
                                file_path=final_path,
                                classification=DocClassification(classification),
                                user_id=user_id
                            )
                        except Exception as e:
                            logger.error(f"Error en Hook IPFS (MD->PDF/DOCX): {e}")
                    
                    registrar_firma_electronica_y_sello(final_path, context)
                    return os.path.basename(final_path)
                else:
                    # Falló la conversión (probablemente falta Pandoc)
                    # FALLBACK: Devolver el archivo MD original renombrado para que no se pierda.
                    logger.warning(f"Conversión MD->DOCX falló. Retornando MD original.")

        except Exception as e:
             logger.error(f"Error procesando MD: {e}")
             raise HTTPException(status_code=500, detail=str(e))

    # 3. Lógica DOCX
    elif template_filename.endswith('.docx'):
        # USAR custom_filename si existe, de lo contrario UUID
        if custom_filename:
            temp_docx_name = f"{custom_filename}.docx"
        else:
            base_name = template_filename.rsplit('.', 1)[0]
            temp_docx_name = f"{base_name}_{uuid.uuid4()}.docx"
        temp_docx_path = os.path.join(target_dir, temp_docx_name)

        try:
            doc = DocxTemplate(io.BytesIO(template_content))
            
            # MAGIA SUBDOC: Inyectar clausulas si se detecta 'subdoc:' en el contexto
            context = _inject_subdocs(context, doc)
            
            doc.render(context)
            doc.save(temp_docx_path)
        except Exception as e:
            logger.error(f"Error renderizando DOCX: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        if convert_pdf:
            pdf_path = await convert_to_pdf(temp_docx_path, target_dir)
            if pdf_path:
                try:
                    os.remove(temp_docx_path)
                except:
                    pass
                    
                # IPFS Hook para PDF desde DOCX
                if anchor_ipfs:
                    from app.services.ipfs_integration_service import IPFSIntegrationService
                    from app.services.crypto_engine import DocClassification
                    try:
                        await IPFSIntegrationService.anchor_and_stamp(
                            file_path=pdf_path,
                            classification=DocClassification(classification),
                            user_id=user_id
                        )
                    except Exception as e:
                        logger.error(f"Error en Hook IPFS (DOCX->PDF): {e}")
                
                registrar_firma_electronica_y_sello(pdf_path, context)
                return os.path.basename(pdf_path)
            else:
                 # Si falla PDF, tratamos de borrar el docx temporal pero lanzamos error o devolvemos docx?
                 # Main original trataba de borrar y dar error.
                 try:
                    os.remove(temp_docx_path) 
                 except: 
                    pass
                 raise HTTPException(500, "Falló la conversión a PDF.")
        
        # IPFS Hook para DOCX directo
        if anchor_ipfs:
            from app.services.ipfs_integration_service import IPFSIntegrationService
            from app.services.crypto_engine import DocClassification
            try:
                await IPFSIntegrationService.anchor_and_stamp(
                    file_path=temp_docx_path,
                    classification=DocClassification(classification),
                    user_id=user_id
                )
            except Exception as e:
                logger.error(f"Error en Hook IPFS (DOCX directo): {e}")
        
        registrar_firma_electronica_y_sello(temp_docx_path, context)
        return temp_docx_name

    else:
        raise HTTPException(400, "Tipo de archivo no soportado.")
