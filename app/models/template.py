from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

class Template(SQLModel, table=True):
    __tablename__ = "templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True, unique=True, nullable=False)
    description: Optional[str] = Field(default=None)
    uploaded_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    
    status: str = Field(default="approved", nullable=False)
    comments: Optional[str] = Field(default=None)
    uploaded_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
