from fastapi import HTTPException


class StarDocException(Exception):
    """Excepción base para toda la aplicación Star-Doc."""
    status_code: int = 500
    detail: str = "Error interno del servidor en Star-Doc"

    def __init__(self, detail: str = None, status_code: int = None):
        if detail:
            self.detail = detail
        if status_code:
            self.status_code = status_code
        super().__init__(self.detail)

    def to_http_exception(self) -> HTTPException:
        """Helper para compatibilidad con código FastAPI existente mientras se refactoriza."""
        return HTTPException(status_code=self.status_code, detail=self.detail)
