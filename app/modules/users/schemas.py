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

# Para recibir los datos del formulario de login
class UsuarioLogin(BaseModel):
    username: str
    password: str

# Para enviar la respuesta tras un login exitoso
class LoginResponse(BaseModel):
    id_usuario: int
    username: str
    rol: str
    status: str = "success"
    # Aquí podrías añadir un access_token más adelante