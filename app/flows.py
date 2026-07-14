# app/flows.py
from pydantic import BaseModel
from genkit.ai import Genkit
from genkit.plugins.google_genai import GoogleAI

# Volvemos a la inicialización documentada. El error de Pydantic lo resolveremos a continuación.
ai = Genkit(
    plugins=[GoogleAI()],
    model='googleai/gemini-2.5-flash'
)

class ClausulaRequest(BaseModel):
    descripcion: str

class ClausulaResponse(BaseModel):
    clausula: str

@ai.flow(
    name="generarClausulaLegal",
    input_schema=ClausulaRequest,
    output_schema=ClausulaResponse,
)
def generar_clausula_legal(request: ClausulaRequest) -> ClausulaResponse:
    """Genera una cláusula legal experta basada en una descripción."""

    system_prompt = ("Actúa como un abogado colombiano con más de 20 años de experiencia en derecho comercial y contractual. "
                     "Tu tarea es redactar cláusulas legales precisas, robustas y adaptadas a la legislación colombiana vigente. "
                     "La cláusula debe ser clara, profesional y lista para ser usada en un contrato real.")

    response = ai.generate(
        prompt=request.descripcion,
        config={
            "system_prompt": system_prompt,
            "temperature": 0.3,
        }
    )

    generated_text = response.text()

    return ClausulaResponse(clausula=generated_text)
