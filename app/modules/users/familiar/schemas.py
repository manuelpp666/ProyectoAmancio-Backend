from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from app.core.util.utils import DniStr, TelefonoStr

class FamiliarBase(BaseModel):
    nombres: str = Field(..., max_length=250)
    apellidos: str = Field(..., max_length=250)
    email: Optional[EmailStr] = None
    direccion: Optional[str] = Field(None, max_length=300)
    tipo_parentesco: Optional[str] = Field(None, max_length=50)

class FamiliarCreate(FamiliarBase):
    dni: DniStr
    telefono: TelefonoStr

class FamiliarResponse(FamiliarBase):
    id_familiar: int
    dni: str
    telefono: str
    model_config = ConfigDict(from_attributes=True)