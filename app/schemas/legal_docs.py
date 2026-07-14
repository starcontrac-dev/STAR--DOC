from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
import re
from datetime import datetime

class TutelaSchema(BaseModel):
    nombre_accionante: str = Field(..., min_length=5, description="Nombre completo de quien presenta la tutela")
    documento_identidad: str = Field(..., description="Cédula o documento de identidad")
    
    # Lógica Menor de Edad
    es_menor: bool = Field(False, description="True si la tutela es para un menor")
    nombre_menor: Optional[str] = Field(None, description="Nombre del menor (requerido si es_menor=True)")
    
    accionado: str = Field(..., min_length=3, description="Entidad o persona contra quien se dirige la tutela (ej: EPS Sanitas)")
    
    # Hechos
    hechos: List[str] = Field(..., min_length=3, description="Lista de hechos cronológicos (mínimo 3)")
    
    # Derechos
    derechos_vulnerados: List[str] = Field(..., min_length=1, description="Lista de derechos fundamentales (ej: Salud, Vida, Petición)")
    
    pretensiones: str = Field(..., min_length=20, description="Qué solicita el juez ordenarle al accionado")
    
    juez_dirigido: str = Field("JUEZ CONSTITUCIONAL (REPARTO)", description="A quién se dirige el escrito")
    ciudad: str = Field(..., description="Ciudad de presentación")
    
    # Juramento de no temeridad (Decreto 2591 de 1991, Art 38)
    juramento_no_temeridad: bool = Field(
        True, 
        description="Indica manifestación bajo juramento de no haber interpuesto otra tutela por los mismos hechos"
    )
    
    @model_validator(mode='after')
    def check_legal_rules(self):
        if self.es_menor and not self.nombre_menor:
            raise ValueError("Si es_menor=True, se requiere 'nombre_menor'.")
        if not self.juramento_no_temeridad:
            raise ValueError(
                "De conformidad con el Artículo 38 del Decreto 2591 de 1991, es obligatorio manifestar "
                "bajo la gravedad del juramento que no se ha presentado otra acción de tutela por los "
                "mismos hechos y derechos ante otra autoridad judicial (Principio de no temeridad)."
            )
        return self

    @field_validator('documento_identidad')
    @classmethod
    def validate_documento(cls, v):
        clean = v.replace('.', '').replace(',', '')
        if not clean.isdigit():
            raise ValueError("El documento de identidad debe contener números.")
        return v
    
    @field_validator('hechos')
    @classmethod
    def validate_hechos(cls, v):
        if len(v) < 3:
            raise ValueError("La tutela debe tener al menos 3 hechos narrados cronológicamente.")
        return v

class ContratoArrendamientoSchema(BaseModel):
    arrendador_nombre: str = Field(..., min_length=5)
    arrendador_cedula: str = Field(...)
    arrendatario_nombre: str = Field(..., min_length=5)
    arrendatario_cedula: str = Field(...)
    
    inmueble_direccion: str = Field(..., min_length=8)
    inmueble_ciudad: str = Field(...)
    
    canon_mensual: float = Field(..., gt=0, description="Canon mensual mayor a 0")
    duracion_meses: int = Field(..., gt=0, description="Duración en meses mayor a 0")
    
    fecha_inicio: str = Field(...)
    
    # Campos adicionales para validar límites legales de vivienda urbana (Ley 820 de 2003)
    valor_comercial_inmueble: Optional[float] = Field(
        None, 
        description="Valor comercial del inmueble para controlar que el canon no exceda el 1% legal (Art. 18 Ley 820)"
    )
    deposito_garantia_efectivo: Optional[bool] = Field(
        False, 
        description="Exigencia ilegal de depósitos en efectivo en vivienda urbana (Art. 20 Ley 820)"
    )

    @model_validator(mode='after')
    def validar_limites_arrendamiento(self):
        # 1. Validación de tope de canon de arrendamiento (Art. 18 de la Ley 820 de 2003)
        if self.valor_comercial_inmueble is not None:
            limite_canon = self.valor_comercial_inmueble * 0.01
            if self.canon_mensual > limite_canon:
                raise ValueError(
                    f"Alerta de Ilegalidad: El canon mensual (${self.canon_mensual:,.2f}) supera el límite legal del 1% del "
                    f"valor comercial del inmueble (${limite_canon:,.2f}) establecido en el Artículo 18 de la Ley 820 de 2003."
                )
        
        # 2. Prohibición de depósitos de garantía en efectivo (Art. 20 de la Ley 820 de 2003)
        if self.deposito_garantia_efectivo:
            raise ValueError(
                "Alerta de Ilegalidad: El Artículo 20 de la Ley 820 de 2003 prohíbe exigir depósitos "
                "de garantía en dinero efectivo o en firmas de pagarés para garantizar obligaciones en vivienda urbana."
            )
        return self

    @field_validator('arrendador_cedula', 'arrendatario_cedula')
    @classmethod
    def validate_cedulas(cls, v):
        clean = v.replace('.', '').replace(',', '')
        if not clean.isdigit():
            raise ValueError("La cédula debe contener números.")
        return v
        
    @field_validator('fecha_inicio')
    @classmethod
    def validate_fecha(cls, v):
        try:
            # Revisa formato básico AAAA-MM-DD
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("La fecha debe tener formato YYYY-MM-DD")
        return v


class ContestacionTutelaSchema(BaseModel):
    radicado: str = Field(..., min_length=10, description="Número de radicación único del proceso de tutela")
    juzgado: str = Field(..., min_length=10, description="Nombre completo del Juzgado ante el cual se contesta la tutela")
    nombre_accionante: str = Field(..., min_length=5, description="Nombre completo del accionante (demandante)")
    nombre_accionado: str = Field(..., min_length=5, description="Nombre completo de la persona o entidad accionada (demandada)")
    pronunciamiento_hechos: List[str] = Field(..., min_length=1, description="Pronunciamiento sobre cada uno de los hechos (es cierto, no es cierto, no nos consta)")
    razones_defensa: str = Field(..., min_length=50, description="Fundamentación de hecho y de derecho que sustenta la defensa y controvierte los cargos")
    solicitud_juez: str = Field(..., min_length=10, description="Petición o pretensión de la defensa al juez de tutela (ej: declarar improcedente o negar el amparo)")
    pruebas: List[str] = Field(..., min_length=1, description="Lista de pruebas que se aportan o se solicitan para desvirtuar la tutela")
    ciudad: str = Field(..., description="Ciudad desde donde se emite la contestación")


class RespuestaPeticionSchema(BaseModel):
    nombre_peticionario: str = Field(..., min_length=5, description="Nombre completo del ciudadano solicitante")
    nombre_entidad: str = Field(..., min_length=5, description="Nombre de la entidad o persona que da respuesta")
    asunto: str = Field(..., min_length=10, description="Asunto de la comunicación")
    respuesta_cuerpo: str = Field(..., min_length=50, description="Cuerpo detallado de la respuesta jurídica resolviendo de fondo lo solicitado")
    documentos_anexos: List[str] = Field(default=[], description="Lista de documentos adjuntos a la respuesta")
    ciudad: str = Field(..., description="Ciudad desde donde se firma la respuesta")


class DerechoPeticionSchema(BaseModel):
    ciudad_fecha: str = Field(..., min_length=5, description="Ciudad y fecha de radicación del escrito")
    entidad_destinataria: str = Field(..., min_length=5, description="Nombre de la entidad o persona receptora de la petición")
    ciudad_destinatario: str = Field(..., min_length=3, description="Ciudad donde se radica la petición")
    nombre_peticionario: str = Field(..., min_length=5, description="Nombre completo del ciudadano que realiza la solicitud")
    cedula_peticionario: str = Field(..., description="Cédula de ciudadanía o identidad del peticionario")
    lugarexp_cedula: str = Field(..., min_length=3, description="Lugar de expedición de la cédula")
    direccion_peticionario: str = Field(..., min_length=8, description="Dirección física del domicilio del peticionario")
    objeto_peticion: str = Field(..., min_length=15, description="Petición concreta de forma clara y precisa")
    razones_peticion: str = Field(..., min_length=30, description="Justificación fáctica o hechos que sustentan la petición")
    lista_documentos: Optional[List[str]] = Field(default=[], description="Lista de anexos documentales aportados")
    direccion_notificacion: str = Field(..., min_length=8, description="Dirección para recibir notificaciones")
    telefono_contacto: str = Field(..., min_length=7, description="Teléfono de contacto")
    email_contacto: str = Field(..., min_length=5, description="Correo electrónico para notificaciones")

    @field_validator('cedula_peticionario')
    @classmethod
    def validate_cedula(cls, v):
        clean = v.replace('.', '').replace(',', '').strip()
        if not clean.isdigit():
            raise ValueError("La cédula de ciudadanía debe contener números.")
        return v


class ContratoTrabajoSchema(BaseModel):
    empleador_nombre: str = Field(..., min_length=5)
    empleador_cedula: str = Field(...)
    empleado_nombre: str = Field(..., min_length=5)
    empleado_cedula: str = Field(...)
    
    cargo: str = Field(..., min_length=3)
    salario_base: float = Field(..., gt=0)
    tipo_contrato: str = Field("indefinido", description="fijo, indefinido, obra_labor")
    duracion_meses: Optional[int] = Field(None, description="Duración en meses para contratos a término fijo")
    periodo_prueba_dias: int = Field(0, ge=0)
    fecha_inicio: str = Field(...)

    @model_validator(mode='after')
    def validar_periodo_prueba(self):
        # 1. Límite general absoluto de 60 días (Art. 78 CST)
        if self.periodo_prueba_dias > 60:
            raise ValueError(
                f"Alerta de Ilegalidad: El período de prueba propuesto ({self.periodo_prueba_dias} días) "
                "no puede exceder el límite absoluto de 60 días establecido en el Artículo 78 del Código Sustantivo del Trabajo."
            )
        
        # 2. Límite de la quinta parte (1/5) para contratos a término fijo (Art. 78 CST)
        if self.tipo_contrato.lower() == "fijo":
            if not self.duracion_meses or self.duracion_meses <= 0:
                raise ValueError("Para contratos a término fijo, se debe especificar la duración en meses para computar límites legales.")
            
            duracion_dias = self.duracion_meses * 30
            limite_quinta_parte = duracion_dias // 5
            if self.periodo_prueba_dias > limite_quinta_parte:
                raise ValueError(
                    f"Alerta de Ilegalidad: Para un contrato a término fijo de {self.duracion_meses} meses ({duracion_dias} días), "
                    f"el período de prueba no puede exceder la quinta parte del término pactado ({limite_quinta_parte} días), "
                    f"según el Artículo 78 del Código Sustantivo del Trabajo. Valor propuesto: {self.periodo_prueba_dias} días."
                )
        return self

    @field_validator('empleador_cedula', 'empleado_cedula')
    @classmethod
    def validate_cedulas(cls, v):
        clean = v.replace('.', '').replace(',', '').strip()
        if not clean.isdigit():
            raise ValueError("La cédula debe contener números.")
        return v

    @field_validator('fecha_inicio')
    @classmethod
    def validate_fecha(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("La fecha debe tener formato YYYY-MM-DD")
        return v



