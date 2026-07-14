"""
Router IPFS para STAR-DOC.

Fachada de agregación que unifica los sub-routers de IPFS
manteniendo la compatibilidad del entrypoint principal.
"""
from fastapi import APIRouter
from app.api.routers.ipfs import core, audits, ipns, webhooks, maintenance

router = APIRouter(prefix="/ipfs", tags=["IPFS & Web3"])

# Incluir sub-routers especializados
router.include_router(core.router)
router.include_router(audits.router)
router.include_router(ipns.router)
router.include_router(webhooks.router)
router.include_router(maintenance.router)
