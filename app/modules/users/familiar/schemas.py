from pydantic import BaseModel
from typing import Optional

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
    id_usuario: Optional[int]
    class Config:
        from_attributes = True