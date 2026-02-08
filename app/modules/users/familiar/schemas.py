from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from app.core.util.utils import DniStr, TelefonoStr

class UsuarioEnFamiliar(BaseModel):
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class FamiliarBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    email: Optional[EmailStr] = None
    direccion: Optional[str] = Field(None, max_length=300)
    tipo_parentesco: Optional[str] = Field(None, max_length=50)

class FamiliarCreate(FamiliarBase):
    dni: DniStr
    telefono: TelefonoStr
    id_usuario: Optional[int] = None

class FamiliarResponse(FamiliarBase):
    id_familiar: int
    dni: str
    telefono: str
    id_usuario: Optional[int] = None # Agregado para integridad
    usuario: Optional[UsuarioEnFamiliar] = None
    model_config = ConfigDict(from_attributes=True)