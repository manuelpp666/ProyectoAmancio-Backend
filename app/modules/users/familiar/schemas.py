from pydantic import BaseModel, ConfigDict
from typing import Optional

class UsuarioEnFamiliar(BaseModel):
    activo: bool
    model_config = ConfigDict(from_attributes=True)

class FamiliarBase(BaseModel):
    dni: str
    nombres: str
    apellidos: str
    telefono: Optional[str]
    email: Optional[str]
    direccion: Optional[str]
    tipo_parentesco: Optional[str]

class FamiliarCreate(FamiliarBase):
    id_usuario: Optional[int] = None

class FamiliarResponse(FamiliarBase):
    id_familiar: int
    usuario: UsuarioEnFamiliar | None = None
    # Pydantic V2 usa model_config en lugar de class Config
    model_config = ConfigDict(from_attributes=True)