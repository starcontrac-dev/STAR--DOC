from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, List


class EmailConfig(BaseModel):
    """Configuración para envío de emails."""
    send_email: bool = False
    recipient_email_template: str = ""
    email_subject_template: str = ""
    email_body_template: str = ""


class GenerateDocumentRequest(BaseModel):
    """Schema para solicitud de generación de documento单个."""
    template_name: Optional[str] = None
    google_doc_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    output_format: str = "docx"
    convert_pdf: bool = False
    email_config: Optional[EmailConfig] = None

    @validator('output_format')
    def validate_output_format(cls, v):
        allowed = ['docx', 'md', 'txt', 'pdf']
        if v not in allowed:
            raise ValueError(f"Formato no soportado. Permitidos: {', '.join(allowed)}")
        return v

    @classmethod
    def from_form(cls, form_data: dict) -> "GenerateDocumentRequest":
        """Convierte form data de multipart/form-data a Pydantic model."""
        # Extraer campos especiales del form
        template_name = form_data.pop('template_name', None)
        google_doc_id = form_data.pop('google_doc_id', None)
        output_format = form_data.pop('output_format', 'docx')
        convert_pdf = form_data.pop('convert_pdf', False)
        
        # Email config
        send_email = form_data.pop('send_email', False)
        email_config = None
        if send_email:
            email_config = EmailConfig(
                send_email=bool(send_email),
                recipient_email_template=form_data.pop('recipient_email_template', ''),
                email_subject_template=form_data.pop('email_subject_template', ''),
                email_body_template=form_data.pop('email_body_template', '')
            )
        
        # El resto es contexto
        context = form_data
        
        return cls(
            template_name=template_name,
            google_doc_id=google_doc_id,
            context=context,
            output_format=output_format,
            convert_pdf=bool(convert_pdf),
            email_config=email_config
        )


class BatchGenerationRequest(BaseModel):
    """Schema para generación en lote."""
    template_source: str  # 'file', 'google_doc', 'template_name'
    template_file: Optional[str] = None
    google_doc_id: Optional[str] = None
    template_name: Optional[str] = None
    data_source: str  # 'file', 'google_sheet'
    google_sheet_id: Optional[str] = None
    output_format: str = "docx"
    convert_pdf: bool = False
    email_config: Optional[EmailConfig] = None
    recipient_email_column: Optional[str] = None

    @validator('output_format')
    def validate_output_format(cls, v):
        allowed = ['docx', 'md', 'txt', 'pdf']
        if v not in allowed:
            raise ValueError(f"Formato no soportado. Permitidos: {', '.join(allowed)}")
        return v

    @validator('template_source')
    def validate_template_source(cls, v, values):
        if v == 'file' and not values.get('template_file'):
            raise ValueError("Debe proporcionar template_file cuando template_source es 'file'")
        if v == 'google_doc' and not values.get('google_doc_id'):
            raise ValueError("Debe proporcionar google_doc_id cuando template_source es 'google_doc'")
        if v == 'template_name' and not values.get('template_name'):
            raise ValueError("Debe proporcionar template_name cuando template_source es 'template_name'")
        return v


class ValidationResultResponse(BaseModel):
    """Respuesta de validación de template vs datos."""
    success: bool
    template_filename: str
    template_vars: List[str]
    data_headers: List[str]
    missing_in_data: List[str]
    unused_in_data: List[str]
    match: bool
    data_quality_errors: Optional[List[str]] = Field(default_factory=list)
    invalid_rows_count: Optional[int] = 0


class TemplateUploadResponse(BaseModel):
    """Respuesta de subida de template."""
    success: bool
    message: str
    filename: Optional[str] = None


class DocumentGenerationResponse(BaseModel):
    """Respuesta de generación de documento."""
    success: bool
    download_url: str
    filename: str
    email_sent_to: Optional[str] = None
