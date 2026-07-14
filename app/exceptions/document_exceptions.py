from fastapi import status
from .base import StarDocException


class TemplateNotFoundError(StarDocException):
    def __init__(self, filename: str):
        super().__init__(
            detail=f"Template '{filename}' not found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class UnauthorizedError(StarDocException):
    def __init__(self, msg: str = "Not authorized"):
        super().__init__(detail=msg, status_code=status.HTTP_403_FORBIDDEN)


class ValidationError(StarDocException):
    def __init__(self, field: str, msg: str):
        super().__init__(
            detail=f"Validation error in '{field}': {msg}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
        )


class DatabaseError(StarDocException):
    def __init__(self, msg: str = "Database error"):
        super().__init__(detail=msg, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
