from pydantic import BaseModel,ConfigDict, Field
from typing import Optional, Literal
from datetime import datetime

class UsuarioBase(BaseModel):
    username: str
    rol: Literal["ADMIN", "DOCENTE", "ALUMNO", "AUXILIAR"] = "ALUMNO"
    activo: bool = True

class UsuarioCreate(UsuarioBase):
    password: str
    rol: Literal["ADMIN", "DOCENTE", "ALUMNO", "CAJERO"] = "ALUMNO"

class UsuarioResponse(UsuarioBase):
    id_usuario: int
    fecha_creacion: datetime
    model_config = ConfigDict(from_attributes=True)

# Para recibir los datos del formulario de login
class UsuarioLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str

# Para enviar la respuesta tras un login exitoso
class LoginResponse(BaseModel):
    id_usuario: int
    username: str
    rol: str
    access_token: str  
    token_type: str = "bearer"
    status: str = "success"
    permisos: Optional[dict] = None
    # True cuando el usuario aún tiene la clave inicial y el colegio
    # exige cambiarla antes de usar el campus.
    debe_cambiar_password: bool = False
    # True cuando la cuenta todavía no tiene un correo de contacto registrado
    # y el colegio exige pedirlo en el primer ingreso.
    debe_registrar_correo: bool = False