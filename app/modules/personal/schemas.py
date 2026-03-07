from pydantic import BaseModel, ConfigDict, Field, EmailStr
from typing import Optional
from decimal import Decimal
from app.core.util.utils import DniStr, TelefonoStr

class PersonalBase(BaseModel):
    dni: DniStr
    nombres: str
    apellidos: str
    telefono: Optional[TelefonoStr] = None
    email: Optional[EmailStr] = None
    sueldo: Decimal = Field(default=Decimal('0.00'), ge=0, decimal_places=2)

class PersonalCreate(PersonalBase):
    password: str

class PersonalUpdate(PersonalBase):
    password: Optional[str] = None

class UsuarioResponse(BaseModel):
    id_usuario: int
    username: str
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class PersonalResponse(PersonalBase):
    id: int  # Unificamos id_admin, id_docente e id_auxiliar para el frontend
    id_usuario: int
    usuario: Optional[UsuarioResponse] = None
    model_config = ConfigDict(from_attributes=True)