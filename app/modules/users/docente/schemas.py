from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.core.util.utils import (
    DniStr, TelefonoStr, DniOpcional, TelefonoOpcional, EmailOpcional,
)
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
    dni: DniStr
    telefono: TelefonoStr

class DocenteUpdate(BaseModel):
    nombres: Optional[str] = Field(None, min_length=1, max_length=250)
    apellidos: Optional[str] = Field(None, min_length=1, max_length=250)
    especialidad: Optional[str] = None
    descripcion: Optional[str] = None
    url_perfil: Optional[str] = None
    # Campos que el formulario puede enviar en blanco: "" se guarda como NULL.
    email: EmailOpcional = None
    dni: DniOpcional = None
    telefono: TelefonoOpcional = None
    visible_web: Optional[bool] = None

class UsuarioEnDocente(BaseModel):
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class DocentePublicoResponse(BaseModel):
    """Lo que puede ver cualquiera desde la web institucional.

    Deliberadamente NO lleva dni, email, telefono ni id_usuario. El nombre de
    usuario del colegio es DOC-<dni>, así que publicar el DNI equivalía a
    publicar media credencial de acceso.
    """
    id_docente: int
    nombres: str
    apellidos: str
    especialidad: str | None = None
    descripcion: Optional[str] = None
    url_perfil: Optional[str] = None
    visible_web: bool = True
    usuario: "UsuarioEnDocente | None" = None
    model_config = ConfigDict(from_attributes=True)


class DocenteResponse(DocenteBase):
    id_docente: int
    dni: str
    # Tolerantes a nulos para no romper la lista si un docente no tiene estos
    # datos. Y tolerantes a "" porque hay filas antiguas guardadas así: con
    # Optional[EmailStr] esa fila reventaba el listado entero.
    email: EmailOpcional = None
    telefono: Optional[str] = None
    visible_web: bool = True
    usuario: UsuarioEnDocente | None = None
    # Pydantic V2 usa model_config en lugar de class Config
    model_config = ConfigDict(from_attributes=True)
