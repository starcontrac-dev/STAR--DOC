from pydantic import BaseModel, EmailStr, field_validator
import re
from typing import Optional, Dict, Any

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres.')
        if not re.search(r"[A-Z]", v):
            raise ValueError('La contraseña debe contener al menos una letra mayúscula.')
        if not re.search(r"\d", v):
            raise ValueError('La contraseña debe contener al menos un número.')
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('La contraseña debe contener al menos un carácter especial.')
        return v

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres.')
        if not re.search(r"[A-Z]", v):
            raise ValueError('La contraseña debe contener al menos una letra mayúscula.')
        if not re.search(r"\d", v):
            raise ValueError('La contraseña debe contener al menos un dígito.')
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('La contraseña debe contener al menos un carácter especial.')
        return v

class UserInDB(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    hashed_password: str
    disabled: bool
    google_credentials: Optional[Dict[str, Any]] = None
    oauth_state: Optional[str] = None

class WalletAddress(BaseModel):
    wallet_address: str

class WalletLogin(BaseModel):
    wallet_address: str
    signature: str

class Token(BaseModel):
    access_token: str
    token_type: str
