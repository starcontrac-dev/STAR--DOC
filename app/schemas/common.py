from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class ScheduleCreate(BaseModel):
    template_name: Optional[str] = None
    google_doc_id: Optional[str] = None
    context: Dict[str, Any]
    output_format: str = 'docx'
    cron_expression: str
    job_id: Optional[str] = None

class JobRead(BaseModel):
    id: str
    name: str
    trigger: str
    next_run_time: Optional[datetime] = None

class GeminiRequest(BaseModel):
    prompt: str
    history: Optional[List[Dict[str, Any]]] = None
    system_instruction: Optional[str] = None
    web_search: Optional[bool] = False
    search_query: Optional[str] = None
    max_search_results: Optional[int] = 3
    document_context: Optional[str] = None
    skill_id: Optional[str] = None
    stream: Optional[bool] = False

