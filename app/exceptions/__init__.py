from .base import StarDocException
from .document_exceptions import (
    TemplateNotFoundError,
    UnauthorizedError,
    ValidationError,
    DatabaseError
)
from .error_handler import add_exception_handlers

__all__ = [
    "StarDocException",
    "TemplateNotFoundError",
    "UnauthorizedError",
    "ValidationError",
    "DatabaseError",
    "add_exception_handlers",
]
