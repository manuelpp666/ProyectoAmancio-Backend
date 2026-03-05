from pydantic import BaseModel, ConfigDict
from typing import Optional
from decimal import Decimal

class PersonalBase(BaseModel):
    dni: str
    nombres: str
    apellidos: str
    telefono: Optional[str] = None
    email: Optional[str] = None
    sueldo: Decimal = Decimal('0.00')

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