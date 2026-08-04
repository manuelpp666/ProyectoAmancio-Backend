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

class PersonalCreate(PersonalBase):
    password: str
    permisos: Optional[dict] = None

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
    permisos: Optional[dict] = None
    model_config = ConfigDict(from_attributes=True)


class AdminPermisosUpdate(BaseModel):
    # Usamos dict para recibir el objeto JSON
    permisos: dict = Field(..., example={"finanzas": True, "academico": {"ver": True, "horarios": True}})

class AdminPermisosResponse(BaseModel):
    id_admin: int
    nombres: str
    apellidos: str
    permisos: Optional[dict]
    model_config = ConfigDict(from_attributes=True)