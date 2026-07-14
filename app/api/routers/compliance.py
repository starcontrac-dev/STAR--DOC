import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.auth import get_current_active_user
from app.models.user import User
from app.models.kyc_audit import KycAudit
from app.database import get_session
from app.schemas.compliance import KycAuditRequest, KycAuditResponse, SyncListsResponse
from app.services.compliance_service import ComplianceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compliance", tags=["Compliance KYC/AML"])

@router.post("/audit", response_model=KycAuditResponse, status_code=status.HTTP_201_CREATED)
async def perform_kyc_audit(
    payload: KycAuditRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Realiza una auditoría KYC / AML en tiempo real para una persona natural o jurídica
    bajo las normativas SARLAFT y SAGRILAFT aplicables en Colombia.
    """
    logger.info(f"Auditoría KYC iniciada por {current_user.email} para: {payload.full_name} ({payload.id_number})")
    try:
        response = await ComplianceService.audit_subject(
            full_name=payload.full_name,
            id_number=payload.id_number,
            document_id=payload.document_id,
            session=session
        )
        return response
    except Exception as e:
        logger.error(f"Error procesando auditoría KYC/AML: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar la auditoría KYC/AML: {str(e)}"
        )

@router.post("/sync-lists", response_model=SyncListsResponse)
async def sync_restrictive_lists(
    current_user: User = Depends(get_current_active_user)
):
    """
    Sincroniza y actualiza los índices locales de listas restrictivas (OFAC y ONU)
    descargando los archivos oficiales directamente y parseándolos a JSON.
    """
    logger.info(f"Sincronización de listas restrictivas solicitada por {current_user.email}")
    try:
        response = await ComplianceService.sync_restrictive_lists()
        return response
    except Exception as e:
        logger.error(f"Error sincronizando listas restrictivas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al sincronizar listas restrictivas: {str(e)}"
        )

@router.get("/history", response_model=List[KycAudit])
async def get_audit_history(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene el historial de auditorías de cumplimiento (KYC/AML) ordenado por fecha de creación descendente.
    """
    try:
        statement = select(KycAudit).order_by(desc(KycAudit.created_at)).limit(limit).offset(offset)
        result = await session.execute(statement)
        audits = result.scalars().all()
        return audits
    except Exception as e:
        logger.error(f"Error obteniendo historial de auditorías: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar el historial de auditorías."
        )

@router.get("/audit/{audit_id}", response_model=KycAudit)
async def get_audit_detail(
    audit_id: int,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Obtiene el detalle completo de un registro de auditoría KYC por su ID.
    """
    try:
        db_audit = await session.get(KycAudit, audit_id)
        if not db_audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auditoría con ID {audit_id} no encontrada."
            )
        return db_audit
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recuperando auditoría {audit_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al recuperar el detalle de la auditoría."
        )
