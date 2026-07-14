from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .base import StarDocException
import logging

logger = logging.getLogger(__name__)


def add_exception_handlers(app: FastAPI):
    """Registra handlers globales de excepciones en la app FastAPI."""

    @app.exception_handler(StarDocException)
    async def stardoc_exception_handler(request: Request, exc: StarDocException):
        logger.error(f"StarDocException atrapada: {exc.detail} (status: {exc.status_code})")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
