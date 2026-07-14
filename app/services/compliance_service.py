import os
import json
import logging
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime
from typing import List, Dict, Any, Tuple
import asyncio
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
import difflib

from app.models.kyc_audit import KycAudit
from app.schemas.compliance import KycAuditResponse, SanctionMatch, SyncListsResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# Directorio de almacenamiento para las listas restrictivas
COMPLIANCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "compliance")
os.makedirs(COMPLIANCE_DIR, exist_ok=True)

OFAC_XML_PATH = os.path.join(COMPLIANCE_DIR, "ofac_sdn.xml")
OFAC_JSON_PATH = os.path.join(COMPLIANCE_DIR, "ofac_index.json")
UN_XML_PATH = os.path.join(COMPLIANCE_DIR, "un_consolidated.xml")
UN_JSON_PATH = os.path.join(COMPLIANCE_DIR, "un_index.json")

class ComplianceService:

    @staticmethod
    async def sync_restrictive_lists() -> SyncListsResponse:
        """
        Descarga de forma asíncrona las listas de OFAC y ONU, las parsea
        y crea índices JSON compactos para acelerar las consultas en memoria.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # 1. Sincronizar OFAC
        logger.info("Iniciando sincronización de lista OFAC (Clinton)...")
        ofac_count = 0
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get("https://www.treasury.gov/ofac/downloads/sdn.xml", headers=headers)
                if response.status_code == 200:
                    # Guardar archivo XML
                    with open(OFAC_XML_PATH, "wb") as f:
                        f.write(response.content)
                    
                    # Parsear en un hilo separado para no bloquear el event loop
                    ofac_count = await asyncio.to_thread(ComplianceService._parse_ofac_xml)
                    logger.info(f"Lista OFAC sincronizada exitosamente con {ofac_count} registros.")
                else:
                    logger.error(f"Error descargando OFAC: status {response.status_code}")
        except Exception as e:
            logger.error(f"Error en sincronización de OFAC: {e}")

        # 2. Sincronizar ONU
        logger.info("Iniciando sincronización de lista Consolidada ONU...")
        un_count = 0
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get("https://scsanctions.un.org/resources/xml/en/consolidated.xml")
                if response.status_code == 200:
                    # Guardar archivo XML
                    with open(UN_XML_PATH, "wb") as f:
                        f.write(response.content)
                    
                    # Parsear en un hilo separado
                    un_count = await asyncio.to_thread(ComplianceService._parse_un_xml)
                    logger.info(f"Lista ONU sincronizada exitosamente con {un_count} registros.")
                else:
                    logger.error(f"Error descargando ONU: status {response.status_code}")
        except Exception as e:
            logger.error(f"Error en sincronización de ONU: {e}")

        success = (ofac_count > 0 or os.path.exists(OFAC_JSON_PATH)) and (un_count > 0 or os.path.exists(UN_JSON_PATH))
        
        return SyncListsResponse(
            success=success,
            message="Sincronización de listas restrictivas completada.",
            ofac_records_count=ofac_count if ofac_count > 0 else ComplianceService._get_cached_count(OFAC_JSON_PATH),
            un_records_count=un_count if un_count > 0 else ComplianceService._get_cached_count(UN_JSON_PATH),
            updated_at=datetime.utcnow()
        )

    @staticmethod
    def _get_cached_count(path: str) -> int:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return len(data)
            except Exception:
                return 0
        return 0

    @staticmethod
    def _parse_ofac_xml() -> int:
        """Parsea el XML de OFAC y guarda un JSON indexado con los nombres y documentos."""
        if not os.path.exists(OFAC_XML_PATH):
            return 0
        
        tree = ET.parse(OFAC_XML_PATH)
        root = tree.getroot()
        
        # El XML de OFAC contiene namespaces
        # Encontramos el namespace de la raíz
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        records = []
        for entry in root.findall(f"{ns}sdnEntry"):
            uid = entry.find(f"{ns}uid").text if entry.find(f"{ns}uid") is not None else ""
            
            # Nombre completo
            first_name = entry.find(f"{ns}firstName").text if entry.find(f"{ns}firstName") is not None else ""
            last_name = entry.find(f"{ns}lastName").text if entry.find(f"{ns}lastName") is not None else ""
            full_name = f"{first_name} {last_name}".strip()
            
            sdn_type = entry.find(f"{ns}sdnType").text if entry.find(f"{ns}sdnType") is not None else "Individual"
            program_list = []
            program_parent = entry.find(f"{ns}programList")
            if program_parent is not None:
                for prog in program_parent.findall(f"{ns}program"):
                    if prog.text:
                        program_list.append(prog.text)
            
            # Recopilar documentos de identificación
            id_list = []
            id_parent = entry.find(f"{ns}idList")
            if id_parent is not None:
                for id_node in id_parent.findall(f"{ns}id"):
                    id_type = id_node.find(f"{ns}idType").text if id_node.find(f"{ns}idType") is not None else ""
                    id_number = id_node.find(f"{ns}idNumber").text if id_node.find(f"{ns}idNumber") is not None else ""
                    id_country = id_node.find(f"{ns}idCountry").text if id_node.find(f"{ns}idCountry") is not None else ""
                    id_list.append({
                        "type": id_type,
                        "number": id_number,
                        "country": id_country
                    })

            records.append({
                "uid": uid,
                "name": full_name,
                "type": sdn_type,
                "programs": program_list,
                "ids": id_list
            })
        
        with open(OFAC_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            
        return len(records)

    @staticmethod
    def _get_xml_text(element, path: str, default: str = "") -> str:
        node = element.find(path)
        return node.text if node is not None and node.text is not None else default

    @staticmethod
    def _parse_un_xml() -> int:
        """Parsea el XML consolidado de la ONU y guarda un JSON indexado."""
        if not os.path.exists(UN_XML_PATH):
            return 0
            
        tree = ET.parse(UN_XML_PATH)
        root = tree.getroot()
        
        records = []
        
        # Buscar en individuos
        individuals = root.find("INDIVIDUALS")
        if individuals is not None:
            for ind in individuals.findall("INDIVIDUAL"):
                data_id = ComplianceService._get_xml_text(ind, "DATAID")
                
                # Armar el nombre completo
                fn = ComplianceService._get_xml_text(ind, "FIRST_NAME")
                sn = ComplianceService._get_xml_text(ind, "SECOND_NAME")
                tn = ComplianceService._get_xml_text(ind, "THIRD_NAME")
                four_n = ComplianceService._get_xml_text(ind, "FOURTH_NAME")
                full_name = " ".join([fn, sn, tn, four_n]).replace("  ", " ").strip()
                
                reason = ComplianceService._get_xml_text(ind, "REASON_FOR_LISTING")
                
                # Documentos
                ids = []
                for p in ind.findall("INDIVIDUAL_DOCUMENT"):
                    doc_type = ComplianceService._get_xml_text(p, "TYPE_OF_DOCUMENT", "Document")
                    num = ComplianceService._get_xml_text(p, "NUMBER")
                    country = ComplianceService._get_xml_text(p, "ISSUING_COUNTRY")
                    ids.append({"type": doc_type, "number": num, "country": country})
                
                records.append({
                    "data_id": data_id,
                    "name": full_name,
                    "type": "Individual",
                    "reason": reason,
                    "ids": ids
                })
                
        # Buscar en entidades
        entities = root.find("ENTITIES")
        if entities is not None:
            for ent in entities.findall("ENTITY"):
                data_id = ComplianceService._get_xml_text(ent, "DATAID")
                full_name = ComplianceService._get_xml_text(ent, "FIRST_NAME")
                reason = ComplianceService._get_xml_text(ent, "REASON_FOR_LISTING")
                
                records.append({
                    "data_id": data_id,
                    "name": full_name,
                    "type": "Entity",
                    "reason": reason,
                    "ids": []
                })
                
        with open(UN_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            
        return len(records)

    @classmethod
    async def audit_subject(cls, full_name: str, id_number: str, document_id: str = None, session: AsyncSession = None) -> KycAuditResponse:
        """
        Realiza una auditoría KYC / AML automatizada.
        Garantiza compliance verificando bases de datos nacionales (Contraloría/Procuraduría)
        y listas internacionales restrictivas (OFAC/ONU).
        """
        # Normalizar datos de entrada
        normalized_name = full_name.strip().upper()
        normalized_id = id_number.replace(".", "").replace("-", "").strip()

        ofac_match = False
        un_match = False
        contraloria_match = False
        procuraduria_match = False
        matches: List[SanctionMatch] = []

        # Asegurar existencia de listas locales sincronizadas
        if not os.path.exists(OFAC_JSON_PATH) or not os.path.exists(UN_JSON_PATH):
            logger.info("Listas locales no encontradas. Ejecutando sincronización inicial...")
            await cls.sync_restrictive_lists()

        # 1. Comprobación en OFAC (Caché local)
        if os.path.exists(OFAC_JSON_PATH):
            try:
                with open(OFAC_JSON_PATH, "r", encoding="utf-8") as f:
                    ofac_data = json.load(f)
                
                for entry in ofac_data:
                    # Coincidencia por documento exacta
                    doc_found = False
                    for doc in entry.get("ids", []):
                        clean_doc = doc.get("number", "").replace(".", "").replace("-", "").strip()
                        if clean_doc and clean_doc == normalized_id:
                            doc_found = True
                            break
                    
                    # Coincidencia por nombre (Fuzzy matching)
                    name_score = difflib.SequenceMatcher(None, entry.get("name", "").upper(), normalized_name).ratio()
                    name_found = name_score > 0.85 or normalized_name in entry.get("name", "").upper()

                    if doc_found or name_found:
                        ofac_match = True
                        matches.append(SanctionMatch(
                            source="OFAC",
                            type="Clinton List / SDN",
                            entity_or_person=entry.get("name", ""),
                            document_matched=normalized_id if doc_found else "Nombre Coincidente (Fuzzy Match)",
                            description=f"Programas asociados: {', '.join(entry.get('programs', []))}",
                            severity="ALTO"
                        ))
            except Exception as e:
                logger.error(f"Error consultando OFAC local: {e}")

        # 2. Comprobación en ONU (Caché local)
        if os.path.exists(UN_JSON_PATH):
            try:
                with open(UN_JSON_PATH, "r", encoding="utf-8") as f:
                    un_data = json.load(f)
                
                for entry in un_data:
                    doc_found = False
                    for doc in entry.get("ids", []):
                        clean_doc = doc.get("number", "").replace(".", "").replace("-", "").strip()
                        if clean_doc and clean_doc == normalized_id:
                            doc_found = True
                            break
                    
                    name_score = difflib.SequenceMatcher(None, entry.get("name", "").upper(), normalized_name).ratio()
                    name_found = name_score > 0.85 or normalized_name in entry.get("name", "").upper()

                    if doc_found or name_found:
                        un_match = True
                        matches.append(SanctionMatch(
                            source="ONU",
                            type="UN Security Council Consolidated List",
                            entity_or_person=entry.get("name", ""),
                            document_matched=normalized_id if doc_found else "Nombre Coincidente (Fuzzy Match)",
                            description=entry.get("reason", "Sin razón explícita en el registro de la ONU"),
                            severity="ALTO"
                        ))
            except Exception as e:
                logger.error(f"Error consultando ONU local: {e}")

        # 3. Consulta asíncrona a la Contraloría (Datos Abiertos)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Filtrar en datos.gov.co por número de identificación exacto
                url = f"https://www.datos.gov.co/resource/jr8e-e8tu.json?n_mero_de_identificaci_n={normalized_id}"
                response = await client.get(url)
                if response.status_code == 200:
                    records = response.json()
                    if records:
                        contraloria_match = True
                        for r in records:
                            matches.append(SanctionMatch(
                                source="Contraloría General",
                                type=r.get("tipo_de_sanci_n_multa", "Responsabilidad Fiscal"),
                                entity_or_person=r.get("raz_n_social_de_la_entidad", full_name),
                                document_matched=r.get("n_mero_de_identificaci_n", normalized_id),
                                description=r.get("descripci_n_o_detalle_resumen", "Sin detalle en el reporte de datos abiertos"),
                                date=r.get("fecha_de_resoluci_n_de_la", "").split("T")[0] if "T" in r.get("fecha_de_resoluci_n_de_la", "") else r.get("fecha_de_resoluci_n_de_la"),
                                severity="RIESGO_ALTO" if "Responsabilidad Fiscal" in r.get("tipo_de_sanci_n_multa", "") else "MEDIO"
                            ))
                else:
                    logger.warning(f"Contraloría API retornó status {response.status_code}")
        except Exception as e:
            logger.error(f"Error consultando Contraloría API: {e}")

        # 4. Consulta asíncrona a la Procuraduría (SIRI - Datos Abiertos)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Buscamos usando trim o comodines en SoQL para evitar problemas de espaciado
                query_url = f"https://www.datos.gov.co/resource/iaeu-rcn6.json?$where=trim(numero_identificacion)='{normalized_id}'"
                response = await client.get(query_url)
                if response.status_code == 200:
                    records = response.json()
                    if records:
                        procuraduria_match = True
                        for r in records:
                            nombre_sancionado = f"{r.get('primer_nombre', '')} {r.get('segundo_nombre', '') or ''} {r.get('primer_apellido', '')} {r.get('segundo_apellido', '') or ''}".replace("  ", " ").strip()
                            matches.append(SanctionMatch(
                                source="Procuraduría General",
                                type=f"Inhabilidad {r.get('tipo_inhabilidad', 'Disciplinario')}",
                                entity_or_person=nombre_sancionado or full_name,
                                document_matched=r.get("numero_identificacion", "").strip(),
                                description=f"Sanción: {r.get('sanciones', 'Sin especificar')} - Autoridad: {r.get('autoridad', 'No especificada')}",
                                date=r.get("fecha_efectos_juridicos"),
                                severity="ALTO" if "COINCIDENCIA" in r.get("tipo_inhabilidad", "") else "MEDIO"
                            ))
                else:
                    # Fallback simple
                    fallback_url = f"https://www.datos.gov.co/resource/iaeu-rcn6.json?numero_identificacion={normalized_id}"
                    res_fallback = await client.get(fallback_url)
                    if res_fallback.status_code == 200:
                        records = res_fallback.json()
                        if records:
                            procuraduria_match = True
                            for r in records:
                                nombre_sancionado = f"{r.get('primer_nombre', '')} {r.get('segundo_nombre', '') or ''} {r.get('primer_apellido', '')} {r.get('segundo_apellido', '') or ''}".replace("  ", " ").strip()
                                matches.append(SanctionMatch(
                                    source="Procuraduría General (Fallback)",
                                    type=f"Inhabilidad {r.get('tipo_inhabilidad', 'Disciplinario')}",
                                    entity_or_person=nombre_sancionado or full_name,
                                    document_matched=r.get("numero_identificacion", "").strip(),
                                    description=f"Sanción: {r.get('sanciones')} - Autoridad: {r.get('autoridad')}",
                                    date=r.get("fecha_efectos_juridicos"),
                                    severity="MEDIO"
                                ))
        except Exception as e:
            logger.error(f"Error consultando Procuraduría API: {e}")

        # Determinar estado y veredicto jurídico (SARLAFT/SAGRILAFT)
        status = "APROBADO"
        verdict_paragraphs = []

        if ofac_match or un_match:
            status = "BLOQUEADO"
            verdict_paragraphs.append(
                f"🚨 **BLOQUEADO AUTOMÁTICAMENTE (Riesgo Crítico de Cumplimiento)**:\n"
                f"El sujeto consultado coincide con los registros de la Lista de Sanciones Consolidada del Consejo de Seguridad "
                f"de las Naciones Unidas (ONU) y/o la lista OFAC (Clinton List) de los Estados Unidos. Según las circulares externas "
                f"vigentes de la Superintendencia Financiera de Colombia (Capítulo IV de la Circular Básica Jurídica) y de la "
                f"Superintendencia de Sociedades (Circular Externa 100-000016 de 2020 - SAGRILAFT), la vinculación de personas "
                f"listadas en estos boletines vinculantes de terrorismo o lavado de activos obliga al **bloqueo inmediato** "
                f"de la relación comercial, denegación del flujo de firmas del contrato y reporte inmediato de operación sospechosa (ROS) "
                f"ante la UIAF (Unidad de Información y Análisis Financiero), bajo sanción penal y administrativa para los administradores."
            )
        elif contraloria_match or procuraduria_match:
            status = "RIESGO_ALTO"
            verdict_paragraphs.append(
                f"⚠️ **ALERTA: RIESGO ALTO (Hallazgos en Entidades Estatales de Control)**:\n"
                f"El sujeto presenta antecedentes o sanciones vigentes reportadas en Colombia por la Contraloría General de la República "
                f"(Responsabilidad Fiscal) y/o la Procuraduría General de la Nación (Inhabilidades/Sanciones Disciplinarias). "
                f"Bajo las mejores prácticas de la Guía de SAGRILAFT de la Superintendencia de Sociedades, este hallazgo denota un factor de "
                f"riesgo legal y reputacional elevado. Se requiere suspender la firma del contrato y someter el caso a un proceso de "
                f"**Debida Diligencia Intensificada (DDI)** por parte del Oficial de Cumplimiento. La firma solo podrá ser autorizada si el "
                f"Oficial de Cumplimiento emite un concepto favorable motivado e implementa controles de mitigación."
            )
        else:
            verdict_paragraphs.append(
                f"✅ **APROBADO (Cumplimiento de Debida Diligencia Satisfactorio)**:\n"
                f"Tras realizar la debida diligencia de SARLAFT/SAGRILAFT mediante el Auditor Automatizado de STAR-DOC, no se encontraron "
                f"coincidencias ni hallazgos activos en listas internacionales vinculantes (OFAC y Consejo de Seguridad de la ONU) ni en "
                f"las bases de datos nacionales oficiales de antecedentes y sanciones del Estado colombiano (Contraloría General y Procuraduría General).\n"
                f"El sujeto cumple a cabalidad con los estándares de cumplimiento normativo y está habilitado para continuar con el flujo contractual."
            )

        verdict = "\n\n".join(verdict_paragraphs)

        # Crear registro en base de datos si se provee sesión
        audit_id = None
        if session is not None:
            try:
                db_audit = KycAudit(
                    document_id=document_id,
                    full_name=full_name,
                    id_number=id_number,
                    status=status,
                    ofac_match=ofac_match,
                    un_match=un_match,
                    contraloria_match=contraloria_match,
                    procuraduria_match=procuraduria_match,
                    details={
                        "verdict": verdict,
                        "matches": [m.dict() for m in matches]
                    }
                )
                session.add(db_audit)
                await session.commit()
                await session.refresh(db_audit)
                audit_id = db_audit.id
            except Exception as e:
                logger.error(f"Error guardando auditoría KYC en BD: {e}")
                await session.rollback()

        return KycAuditResponse(
            success=True,
            audit_id=audit_id,
            full_name=full_name,
            id_number=id_number,
            status=status,
            verdict=verdict,
            ofac_match=ofac_match,
            un_match=un_match,
            contraloria_match=contraloria_match,
            procuraduria_match=procuraduria_match,
            matches=matches,
            created_at=datetime.utcnow()
        )
