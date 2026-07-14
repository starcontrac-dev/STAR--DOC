"""
Paquete de Herramientas del Agente de IA STAR-DOC.

Este paquete contiene:
- registry: Patrón Registry para registro dinámico de herramientas
- schemas: Definiciones de schemas de herramientas para Gemini API
- dispatcher: Despachador central que ejecuta herramientas por nombre
- handlers/: Módulos individuales con la lógica de cada herramienta

Uso desde ai.py:
    from app.api.tools import execute_tool, TOOLS_SCHEMA
"""

# Importar handlers para que se auto-registren al cargar el paquete
from app.api.tools.handlers import (  # noqa: F401 - Los imports disparan el registro
    template_handlers,
    document_handlers,
    search_handlers,
    validation_handlers,
    nlp_handlers,
    notebook_handlers,
    expedientes_handlers,
    ipfs_handlers,
    rag_handlers,
)

# Interfaz pública del paquete
from app.api.tools.schemas import TOOLS_SCHEMA  # noqa: F401
from app.api.tools.dispatcher import execute_tool  # noqa: F401
