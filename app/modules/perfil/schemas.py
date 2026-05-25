from pydantic import BaseModel, Field
from typing import Optional

class ChangePasswordSchema(BaseModel):
    username: str
    current_password: str
    new_password: str = Field(..., min_length=8)

class ActualizarPerfilAdminSchema(BaseModel):
    telefono: Optional[str] = None
    email: Optional[str] = None
    url_perfil: Optional[str] = None