from pydantic import BaseModel,ConfigDict
from typing import Optional
from datetime import datetime

class UsuarioBase(BaseModel):
    username: str
    rol: str
    activo: bool = True

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    id_usuario: int
    fecha_creacion: datetime
    model_config = ConfigDict(from_attributes=True)