from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.core.util.utils import DniStr, TelefonoStr
from typing import Optional


class DocenteBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    especialidad: str | None = Field(default=None, max_length=100)
    descripcion: Optional[str] = None
    url_perfil: Optional[str] = Field(default=None, max_length=255)
    email: EmailStr
    id_usuario: int | None = None

class DocenteCreate(DocenteBase):
    # Ya no necesitas las líneas de validator(...)
    # Al usar DniStr, la validación ocurre automáticamente
    dni: DniStr
    telefono: TelefonoStr

class DocenteUpdate(BaseModel):
    nombres: Optional[str] = None
    apellidos: Optional[str] = None
    especialidad: Optional[str] = None
    descripcion: Optional[str] = None
    url_perfil: Optional[str] = None
    email: Optional[EmailStr] = None
    dni: Optional[DniStr] = None
    telefono: Optional[TelefonoStr] = None

class UsuarioEnDocente(BaseModel):
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class DocenteResponse(DocenteBase):
    id_docente: int
    dni: str
    telefono: str
    usuario: UsuarioEnDocente | None = None
    # Pydantic V2 usa model_config en lugar de class Config
    model_config = ConfigDict(from_attributes=True)
